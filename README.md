# Custom CNC Controller

Touchscreen-first CNC and laser controller prototype for GRBL machines, targeting an ODROID-XU4 with a 7-inch 1024x600 HDMI touchscreen.

## Current scope

This repository is currently an application scaffold, not a finished CNC controller. The CNC Mode button launches bCNC, which supplies jogging, probing, work coordinates, G-code preview, and GRBL job sending. The controller also loads machine profile and material data, analyzes G-code bounds/feed/power, validates job settings with safety rules, and routes simulated hardware-control events. It does not yet parse SVG/DXF/Gerber files or drive ODROID GPIO controls.

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
sudo apt install python3-tk
python -m pip install -e ".[cnc]"
python -m cnc_controller.ui.app
```

The default launcher runs `python -m bCNC`. To use a system package, checkout,
or wrapper script instead, set `CNC_CONTROLLER_BCNC_COMMAND` to the desired
command before starting the controller.

## Safety model

Jobs are checked against the selected machine profile, material/tool limits, laser S range, pass count, and XY job bounds before sending.

## Background backend work

The current backend code is intentionally hardware-independent so development can continue while the enclosure, buttons, and encoders are still being designed. Added pieces include:

- G-code comment stripping, word parsing, and simple XY/feed/power analysis.
- Job file mode detection for common G-code and vector extensions.
- Material/tool safety rule loading and lookup.
- A hardware input router that can later be connected to GPIO buttons and encoders.
- Workflow step definitions for CNC, laser, and PCB modes.
