# CNC·CTRL

Custom touchscreen GRBL machine controller for a 7-inch 1024×600 display.
Targets Linux SBCs (ODROID-XU4, Raspberry Pi) with GRBL over USB serial.

## Architecture

```
src/cnc_controller/
├── grbl.py            — basic GRBL serial facade
├── grbl_worker.py     — QThread real-time GRBL I/O + job streaming
├── mock_serial.py     — simulated GRBL serial for development
├── models.py          — MachineProfile, JobSettings, SafetyReport
├── gcode.py           — G-code parser / analyser
├── safety.py          — pre-flight job checks
├── jobs.py            — job file loading
└── ui/
    ├── app.py         — QMainWindow, AppController, screen navigation
    ├── theme.py       — design tokens + Qt stylesheet
    ├── qt_compat.py   — PySide6 / PyQt5 import shim
    ├── widgets/
    │   ├── status_bar.py   — 46 px top bar
    │   └── action_rail.py  — 104 px right rail
    └── screens/
        ├── splash.py        — startup loading screen
        ├── home.py          — mode picker + machine status
        ├── cnc_mode.py      — DRO, jog pad, job streaming
        ├── laser_mode.py    — layer settings, preview, run
        ├── file_browser.py  — USB/SD/internal file picker
        ├── probing.py       — Z probe macro + probe type picker
        ├── safety_review.py — pre-flight checklist
        └── settings.py      — machine, display, GRBL settings
```

## Install

### Desktop development (Windows / Linux / Mac)

```bash
pip install PySide6 pyserial
pip install -e .
```

### Raspberry Pi / ODROID (ARM64)

```bash
pip install PySide6 pyserial      # or: sudo apt install python3-pyside2
pip install -e .
```

### ARM32 (ODROID-XU4 / older Pi)

PySide6 may not have ARM32 wheels. Use PyQt5 instead — the code auto-detects:

```bash
sudo apt install python3-pyqt5 python3-serial
pip install -e .
```

## Run

```bash
# Development — no hardware needed (simulated GRBL)
python -m cnc_controller.ui.app --mock

# Real hardware
python -m cnc_controller.ui.app --port /dev/ttyUSB0

# Kiosk mode (fullscreen, no title bar)
python -m cnc_controller.ui.app --port /dev/ttyUSB0 --fullscreen
```

Or use the installed entry point:

```bash
cnc-controller --mock
```

## Keyboard shortcuts (development)

| Key | Action |
|-----|--------|
| `H` | Go to Home screen |
| `Backspace` | Navigate back |
| `1` | CNC Mode |
| `2` | Laser Mode |
| `3` | Probing |
| `4` | File Browser |
| `5` | Settings |
| `Space` | Cycle Start (in CNC mode) |
| `F` | Feed Hold (in CNC mode) |
| `Arrow keys` | Jog X/Y (in CNC mode) |
| `Page Up/Down` | Jog Z (in CNC mode) |
| `Escape` | Soft Reset |

## Auto-deploy to Pi

Push to `main` on GitHub. The Pi pulls automatically.

To SSH in manually:

```bash
ssh quentin@quentinpi   # password: quentin
```

## Design language

Based on the Claude Design mockup. Key tokens:

| Token | Value | Use |
|-------|-------|-----|
| Green `#109a5b` | Primary | Ready, confirm, run |
| Blue `#1577d4` | Info | Active job, axis labels |
| Amber `#d98a0a` | Warning | Feed hold, caution |
| Red `#d23b2f` | Danger | Stop, alarm, abort |
| Background | `#e9ecef` | Screen background |
| Card | `#ffffff` | Panel background |

Layout: 46 px status bar (top) + 104 px action rail (right) + content area.

## Physical controls (GPIO — future)

| Button | Action |
|--------|--------|
| Cycle Start | `~` cycle start |
| Feed Hold | `!` feed hold |
| Reset | `\x18` soft reset |
| Probe | Navigate to Probing screen |
| Context | Screen-specific action |
| Encoder 1 | Jog / navigate |
| Encoder 2 | Feed override / power |

## Tests

```bash
pytest
```

Backend is testable without a display — no Qt required in tests.

## Where bCNC logic can be reused

- **G-code sender/streaming** — `bCNC/bCNC/sender.py` has a battle-tested buffer-managed streaming implementation that can replace the simple-streaming approach in `grbl_worker.py`
- **G-code preview rendering** — `bCNC/bCNC/CNCCanvas.py` draws toolpaths with OpenGL; can be adapted for the Job Preview canvas
- **Probe macros** — `bCNC/bCNC/Pendant.py` and plugins contain XYZ corner, bore-center, and edge-find macros
- **GRBL settings ($)** — `bCNC/bCNC/GrblSettings.py` knows all `$` parameter names and types
