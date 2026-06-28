"""Narrow adapter around Rayforge's non-UI modules.

Rayforge is optional during desktop UI development.  Imports are deliberately
lazy because Rayforge's GTK runtime is not available on every target host.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .domain import (
    LaserJob,
    LaserMachineConfig,
    LaserOperationType,
)


@dataclass(frozen=True)
class RayforgeScan:
    layers: list[dict[str, Any]]
    natural_size_mm: tuple[float, float] | None
    warnings: list[str]
    errors: list[str]


@dataclass(frozen=True)
class RayforgeGeneration:
    gcode_lines: list[str]
    estimated_seconds: float | None
    warnings: list[str]


class RayforgeUnavailable(RuntimeError):
    pass


class RayforgeGenerationError(RuntimeError):
    pass


class RayforgeAdapter:
    """Expose only stable backend seams used by the operator frontend.

    Current Rayforge module ownership:
      * file import: ``rayforge.image`` and ``image.registry``
      * job/layers: ``rayforge.core.doc``, ``core.layer``, ``core.workflow``
      * operations: ``rayforge.core.step`` plus laser-essential step add-on
      * generation: ``rayforge.pipeline`` and ``pipeline.encoder.gcode``
      * GRBL: ``rayforge.machine.driver.grbl`` / ``machine.transport.grbl``
      * settings: ``rayforge.machine.models.machine`` / ``machine.device``
    """

    @staticmethod
    def available() -> bool:
        try:
            import rayforge.image  # noqa: F401
        except (ImportError, OSError):
            return False
        return True

    def scan(self, path: Path) -> RayforgeScan:
        if not self.available():
            raise RayforgeUnavailable(
                "Rayforge is not installed; vector/raster generation is unavailable."
            )

        # Importing rayforge.image populates the registry with built-in
        # SVG/DXF/PDF/raster importers.
        from rayforge.image import importer_registry

        importer_cls = importer_registry.get_for_file(path)
        if importer_cls is None:
            return RayforgeScan([], None, [], [f"Rayforge has no importer for {path.suffix}."])
        importer = importer_cls(path.read_bytes(), source_file=path)
        manifest = importer.scan()
        layers = [
            {
                "name": info.name,
                "color": self._color_to_hex(info.color),
                "feature_count": info.feature_count,
                "enabled": info.default_active,
            }
            for info in manifest.layers
        ]
        return RayforgeScan(
            layers=layers,
            natural_size_mm=manifest.natural_size_mm,
            warnings=list(manifest.warnings),
            errors=list(manifest.errors),
        )

    def generate(
        self, job: LaserJob, machine_config: LaserMachineConfig
    ) -> RayforgeGeneration:
        """Generate GRBL G-code using Rayforge's headless compute stages."""
        if not self.available():
            raise RayforgeUnavailable(
                "Rayforge 1.8 or newer is required to generate artwork."
            )
        try:
            return self._generate_with_rayforge(job, machine_config)
        except (RayforgeUnavailable, RayforgeGenerationError):
            raise
        except Exception as exc:
            raise RayforgeGenerationError(
                f"Rayforge could not generate {job.name}: {exc}"
            ) from exc

    def _generate_with_rayforge(
        self, job: LaserJob, machine_config: LaserMachineConfig
    ) -> RayforgeGeneration:
        self._require_supported_version()

        from rayforge.context import get_context
        from rayforge.core.doc import Doc
        from rayforge.core.layer import Layer
        from rayforge.core.vectorization_spec import (
            LayerImportMode,
            PassthroughSpec,
        )
        from rayforge.image import import_file
        from rayforge.machine.models.machine import Machine, Origin
        from rayforge.pipeline.stage.job_compute import compute_job_artifact
        from rayforge.pipeline.stage.step_compute import compute_step_artifacts
        from rayforge.pipeline.stage.workpiece_compute import (
            compute_workpiece_artifact,
        )

        context = get_context()
        context._headless = True
        contour_step, engrave_step = self._load_laser_step_classes()
        machine = self._create_headless_machine(context, Machine)
        self._configure_machine(machine, machine_config, Origin)

        spec = None
        if job.source_path.suffix.casefold() in {".svg", ".dxf", ".pdf"}:
            spec = PassthroughSpec(
                layer_import_mode=LayerImportMode.NEW_LAYERS
            )
        payload = import_file(job.source_path, vectorization_spec=spec)
        if payload is None or not payload.items:
            raise RayforgeGenerationError(
                "Rayforge imported no usable geometry from the file."
            )

        doc = self._build_document(Doc, Layer, payload)
        rayforge_layers = [
            layer for layer in doc.layers if layer.all_workpieces
        ]
        if not rayforge_layers:
            raise RayforgeGenerationError(
                "Rayforge found no workpieces to generate."
            )

        enabled_settings = [layer for layer in job.layers if layer.enabled]
        if not enabled_settings:
            raise RayforgeGenerationError(
                "At least one operation layer must be enabled."
            )

        step_artifacts: dict[str, Any] = {}
        warnings: list[str] = []
        head = machine.get_default_head()

        for index, rf_layer in enumerate(rayforge_layers):
            settings = self._match_layer(job, rf_layer.name, index)
            workflow = rf_layer.workflow
            if workflow is None:
                continue
            workflow.set_steps([])
            if settings is None or not settings.enabled:
                continue

            step_cls = (
                engrave_step
                if settings.operation
                in {LaserOperationType.FILL, LaserOperationType.RASTER}
                else contour_step
            )
            step = self._configure_step(
                step_cls, settings, machine, head
            )
            workflow.add_step(step)

            producer = step_cls.PRODUCER_CLASS()
            task_settings = step.get_settings()
            task_settings.update(
                {
                    "machine_supports_arcs": machine.supports_arcs,
                    "machine_supports_curves": machine.supports_curves,
                    "arc_tolerance": machine.arc_tolerance,
                }
            )

            workpiece_artifacts = []
            for workpiece in rf_layer.all_workpieces:
                hydrated = workpiece.in_world()
                artifact = compute_workpiece_artifact(
                    workpiece=hydrated,
                    opsproducer=producer,
                    laser=head,
                    transformers=[],
                    settings=task_settings,
                    pixels_per_mm=step.pixels_per_mm,
                    generation_size=workpiece.size,
                    generation_id=1,
                )
                if artifact is not None:
                    workpiece_artifacts.append(
                        (
                            artifact,
                            workpiece.get_world_transform(),
                            workpiece,
                        )
                    )

            if not workpiece_artifacts:
                warnings.append(
                    f"{rf_layer.name}: Rayforge generated no operations."
                )
                continue
            step_artifact = compute_step_artifacts(
                artifacts=workpiece_artifacts,
                transformers=[],
                generation_id=1,
            )
            if settings.passes > 1:
                original = step_artifact.ops.copy()
                for _ in range(1, settings.passes):
                    step_artifact.ops.extend(original.copy())
            step_artifacts[step.uid] = step_artifact

        if not step_artifacts:
            raise RayforgeGenerationError(
                "Rayforge generated no enabled laser operations."
            )
        artifact = compute_job_artifact(
            doc=doc,
            step_artifacts_by_uid=step_artifacts,
            machine=machine,
            generation_id=1,
        )
        machine_code = artifact.machine_code
        if not machine_code or not machine_code.strip():
            raise RayforgeGenerationError(
                "Rayforge returned an empty machine-code artifact."
            )
        return RayforgeGeneration(
            gcode_lines=machine_code.splitlines(),
            estimated_seconds=artifact.time_estimate,
            warnings=warnings,
        )

    @staticmethod
    def _require_supported_version() -> None:
        from importlib.metadata import PackageNotFoundError, version

        try:
            raw_version = version("rayforge")
        except PackageNotFoundError:
            # Editable source checkouts do not always expose metadata.
            return
        try:
            major, minor = (
                int(part) for part in raw_version.split(".", 2)[:2]
            )
        except ValueError:
            return
        # Editable/source installs commonly report 0.0.1 because the
        # setuptools Git version hook has no release metadata available.
        if major != 0 and (major, minor) < (1, 8):
            raise RayforgeUnavailable(
                f"Rayforge {raw_version} is installed; version 1.8+ is required."
            )

    @staticmethod
    def _configure_machine(machine, config, origin_cls) -> None:
        machine.name = config.name
        machine.driver_name = None
        machine.dialect_uid = "grbl"
        machine.origin = origin_cls.BOTTOM_LEFT
        machine.max_cut_speed = round(config.safe_travel_speed_mm_min)
        machine.max_travel_speed = round(config.safe_travel_speed_mm_min)
        head = machine.get_default_head()
        head.max_power = config.laser_s_range[1]
        head.frame_speed = round(config.frame_speed_mm_min)

    @staticmethod
    def _create_headless_machine(context, machine_cls):
        """Construct Machine without starting Rayforge's process manager.

        The custom frontend runs the compute stages synchronously in its own
        QThread, so Rayforge's TaskManager is neither needed nor desirable.
        """
        from rayforge.shared.tasker import task_mgr

        class _Scheduler:
            @staticmethod
            def schedule_on_main_thread(callback, *args, **kwargs):
                return callback(*args, **kwargs)

        previous = task_mgr._instance
        task_mgr._instance = _Scheduler()
        try:
            machine = machine_cls(context)
        finally:
            task_mgr._instance = previous
        # Capability defaults look up get_context().machine. Supply an
        # in-memory config so Rayforge does not load user profiles or start
        # its multiprocessing TaskManager.
        from types import SimpleNamespace

        from rayforge.core.config import Config

        config = Config()
        config.set_machine(machine)
        context._config = config
        context._config_mgr = SimpleNamespace(config=config)
        return machine

    @staticmethod
    def _load_laser_step_classes():
        """Load backend-only built-in add-on modules without GTK."""
        import importlib.util
        import sys
        import types
        from pathlib import Path

        import rayforge

        package_root = (
            Path(rayforge.__file__).resolve().parent
            / "builtin_addons"
            / "rayforge-addon-laser"
            / "laser_essentials"
        )
        if not package_root.exists():
            raise RayforgeGenerationError(
                "Rayforge's built-in laser add-on is missing."
            )

        def namespace(name: str, path: Path):
            module = sys.modules.get(name)
            if module is None:
                module = types.ModuleType(name)
                module.__path__ = [str(path)]
                module.__package__ = name
                sys.modules[name] = module
            return module

        def load(name: str, path: Path):
            existing = sys.modules.get(name)
            if existing is not None:
                return existing
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise RayforgeGenerationError(
                    f"Cannot load Rayforge module {name}."
                )
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module

        try:
            namespace("laser_essentials", package_root)
            producers_path = package_root / "producers"
            producers = namespace(
                "laser_essentials.producers", producers_path
            )
            contour_producer = load(
                "laser_essentials.producers.contour_producer",
                producers_path / "contour_producer.py",
            )
            # Rayforge 1.8.0 on PyPI used the pre-0.13 title-case name
            # while raygeo 0.13 exposes constants in uppercase. Upstream
            # Rayforge has corrected this; retain compatibility with the
            # published wheel.
            from raygeo.ops.raster import ScanMode

            if not hasattr(ScanMode, "Segmented"):
                ScanMode.Segmented = ScanMode.SEGMENTED
            raster_producer = load(
                "laser_essentials.producers.raster_producer",
                producers_path / "raster_producer.py",
            )
            producers.ContourProducer = contour_producer.ContourProducer
            producers.Rasterizer = raster_producer.Rasterizer
            producers.DepthMode = raster_producer.DepthMode

            steps_path = package_root / "steps"
            namespace("laser_essentials.steps", steps_path)
            contour_step = load(
                "laser_essentials.steps.contour_step",
                steps_path / "contour_step.py",
            )
            raster_step = load(
                "laser_essentials.steps.raster_step",
                steps_path / "raster_step.py",
            )
        except (ImportError, AttributeError, OSError) as exc:
            raise RayforgeGenerationError(
                f"Rayforge laser steps could not load: {exc}"
            ) from exc
        return contour_step.ContourStep, raster_step.EngraveStep

    @staticmethod
    def _build_document(doc_cls, layer_cls, payload):
        doc = doc_cls()
        doc.add_asset(payload.source)
        for asset in payload.assets:
            doc.add_asset(asset)

        imported_layers = [
            item for item in payload.items if isinstance(item, layer_cls)
        ]
        loose_items = [
            item for item in payload.items if not isinstance(item, layer_cls)
        ]
        if imported_layers:
            doc.set_layers(imported_layers)
            target = imported_layers[0]
        else:
            doc.set_layers([doc.active_layer])
            target = doc.active_layer
        for item in loose_items:
            target.add_child(item)
        return doc

    @staticmethod
    def _match_layer(job: LaserJob, name: str, index: int):
        normalized = name.casefold().strip()
        for layer in job.layers:
            if layer.name.casefold().strip() == normalized:
                return layer
        return job.layers[index] if index < len(job.layers) else None

    @staticmethod
    def _configure_step(step_cls, settings, machine, head):
        step = step_cls(name=settings.name)
        step.opsproducer_dict = step_cls.PRODUCER_CLASS().to_dict()
        step.per_workpiece_transformers_dicts = []
        step.per_step_transformers_dicts = []
        step.selected_laser_uid = head.uid
        step.max_power = head.max_power
        step.power = settings.power_percent / 100.0
        step.cut_speed = round(settings.speed_mm_min)
        step.travel_speed = round(machine.max_travel_speed)
        step.max_cut_speed = round(machine.max_cut_speed)
        step.max_travel_speed = round(machine.max_travel_speed)
        step.pixels_per_mm = (10, 10)
        step.kerf_mm = head.spot_size_mm[0]
        return step

    @staticmethod
    def _color_to_hex(color: tuple[float, float, float] | None) -> str:
        if color is None:
            return "#1577d4"
        values = [round(max(0.0, min(1.0, channel)) * 255) for channel in color]
        return "#" + "".join(f"{value:02x}" for value in values)
