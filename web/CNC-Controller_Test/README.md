# CNC Controller browser emulator

Static, dependency-free test page for `quentinengineering.com/CNC-Controller_Test`.

- Emulates the 1024×600 touchscreen and current laser workflow.
- Scales the exact controller viewport to the browser width.
- Includes mock file selection, presets, safety review, run progress, console,
  settings, network keyboard, and update status.
- Includes eight inert physical buttons and one inert rotary encoder. These
  provide visual press/rotation feedback only and dispatch no machine actions.
- Sends no network or machine-control commands.

Serve this directory as static files. `index.html`, `styles.css`, and `app.js`
must remain together.

## XU4 deployment

The production XU4 runs `scripts/xu4-web-sync` every five minutes through
`deploy/xu4/cnc-controller-web-sync.timer`. The script:

1. Fast-forwards a clean checkout of this repository.
2. Synchronizes only this directory into
   `/home/quentin/Quentin-Portfolio/project/CNC-Controller_Test`.
3. Records the result in
   `~/.local/state/cnc-controller-web/last-sync.txt`.

The rest of the portfolio checkout is never modified by this sync.
