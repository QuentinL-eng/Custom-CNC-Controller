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
