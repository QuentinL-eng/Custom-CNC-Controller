# Custom CNC Controller

Touchscreen-first CNC and laser controller prototype for GRBL machines, targeting a Raspberry Pi 3B with a 7-inch 1024x600 HDMI touchscreen.

## Current scope

This repository is currently an application scaffold, not a finished CNC controller. It can display the 1024x600 touchscreen home screen, load machine profile and material data, analyze basic G-code bounds/feed/power, validate job settings with safety rules, route simulated hardware-control events, and format a small set of GRBL commands through a testable serial facade. It does not yet stream complete jobs, render previews, parse SVG/DXF/Gerber files, or drive Raspberry Pi GPIO controls.

This repository now contains the first application scaffold for combining:

- bCNC-style GRBL sending and CNC workflows.
- Rayforge/LightBurn-style simple laser job preparation.
- A Haas-inspired touchscreen home screen for CNC, laser, PCB, files, settings, and shutdown.

The code is intentionally modular so the complex sender, preview, SVG/DXF, and PCB workflows can be filled in without binding the project to a single machine.

## Hardware controls

The planned control surface maps to these actions:

- Cycle Start
- Feed Hold
- Reset
- Probe Z
- Mode / Context
- Jog/menu encoder
- Feed override, laser power, or spindle speed encoder

## Run the UI shell

```bash
python -m cnc_controller.ui.app
```

## Safety model

Jobs are checked against the selected machine profile, material/tool limits, laser S range, pass count, and XY job bounds before sending.

## Background backend work

The current backend code is intentionally hardware-independent so development can continue while the enclosure, buttons, and encoders are still being designed. Added pieces include:

- G-code comment stripping, word parsing, and simple XY/feed/power analysis.
- Job file mode detection for common G-code and vector extensions.
- Material/tool safety rule loading and lookup.
- A hardware input router that can later be connected to GPIO buttons and encoders.
- Workflow step definitions for CNC, laser, and PCB modes.
