# Roadmap

## Phase 1: Touchscreen and GRBL foundation

- 1024x600 home screen with CNC Mode, Laser Mode, PCB Wizard, Files, Settings, and Shutdown.
- GRBL serial facade for connect, mode switching, reset, cycle start, feed hold, jogging, and Z probing.
- Machine profiles for GRBL machines, including Cubiko defaults.
- Safety checks for bounds, feed, power, and pass count.
- Hardware-independent G-code analysis, job loading, material rules, input routing, and workflow state primitives.

## Phase 2: CNC mode

- bCNC-style sender queue and status polling.
- G-code preview.
- Work zero controls.
- One-button Z probing.
- Manual tool-change flow that preserves X/Y zero and reprobes only Z.

## Phase 3: Laser mode

- `$32=1` laser mode switching.
- SVG/DXF/G-code loading.
- Rayforge-style vector pipeline for simple jobs.
- Speed, power, pass, frame, and run controls.
- Optional LightBurn interoperability.

## Phase 4: PCB wizard

- Copper Gerber, drill, and optional cutout file inputs.
- FlatCAM-style isolation, drilling, and cutout generation.
- Tool-change prompts with Z reprobe between tools.
- Fixed X/Y origin across all PCB operations.

## Phase 5: Hardware integration

- GPIO button bindings.
- Rotary encoder navigation and overrides.
- Recent jobs, USB/SD import, and network upload.
