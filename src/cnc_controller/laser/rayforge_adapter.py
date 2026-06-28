"""Narrow adapter around Rayforge's non-UI modules.

Rayforge is optional during desktop UI development.  Imports are deliberately
lazy because Rayforge's GTK runtime is not available on every target host.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RayforgeScan:
    layers: list[dict[str, Any]]
    natural_size_mm: tuple[float, float] | None
    warnings: list[str]
    errors: list[str]


class RayforgeUnavailable(RuntimeError):
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

    @staticmethod
    def _color_to_hex(color: tuple[float, float, float] | None) -> str:
        if color is None:
            return "#1577d4"
        values = [round(max(0.0, min(1.0, channel)) * 255) for channel in color]
        return "#" + "".join(f"{value:02x}" for value in values)
