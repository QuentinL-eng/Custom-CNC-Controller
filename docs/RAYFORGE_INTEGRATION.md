# Rayforge backend integration

The touchscreen frontend does not import or subclass Rayforge GTK widgets.
`cnc_controller.laser.rayforge_adapter` is the only Rayforge-facing boundary.
This keeps the 1024×600 operator UI replaceable and testable without GTK.

Rayforge backend ownership, verified against the current upstream source:

| Responsibility | Rayforge modules reused or targeted |
|---|---|
| File import and validation | `rayforge.image`, `rayforge.image.registry`, format importers under `rayforge.image.*` |
| Document and layer model | `rayforge.core.doc`, `rayforge.core.layer`, `rayforge.core.workpiece` |
| Operation setup | `rayforge.core.workflow`, `rayforge.core.step`, laser-essential step add-on |
| Job computation | `rayforge.pipeline`, `rayforge.pipeline.stage.job_compute` |
| G-code encoding | `rayforge.pipeline.encoder.gcode`, `Machine.encode_ops()` |
| GRBL communication | `rayforge.machine.driver.grbl`, `rayforge.machine.transport.grbl` |
| Device settings/profile | `rayforge.machine.models.machine`, `rayforge.machine.device.profile` |

The adapter calls Rayforge's importer registry and phase-one `scan()` contract
to obtain layers, dimensions, warnings, and errors. During generation it
constructs a Rayforge `Doc`, attaches the imported payload, maps enabled UI
layers to `ContourStep` or `EngraveStep`, and runs Rayforge's workpiece, step,
and job compute stages. The resulting `JobArtifact.machine_code` and runtime
estimate are returned to the operator workflow.

Generated lines are never rewritten. They are analyzed exactly as emitted and
must pass the controller's bounds, unsupported-command, rapid-laser, material,
and confirmed `$32=1` checks before the sender enables Start.

The `laser` install extra pins Rayforge to the upstream revision validated by
this controller. The PyPI 1.8.0 wheel declares an incompatible `raygeo` API and
must not be substituted for the pinned source revision.
