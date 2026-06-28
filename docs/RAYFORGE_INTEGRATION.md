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

The first integration slice calls Rayforge's importer registry and phase-one
`scan()` contract to obtain layers, dimensions, warnings, and errors. Existing
G-code can be validated, framed, reviewed, and streamed without Rayforge.
Vector/raster jobs remain non-runnable until Rayforge has produced G-code;
the frontend never substitutes an approximate converter or silently rewrites
machine code.

The next backend slice should construct a Rayforge `Doc`, attach imported
payload items and laser workflow steps, then consume the pipeline's
`JobArtifact.encoded_output`. That work stays inside the adapter and does not
change the touchscreen screens.
