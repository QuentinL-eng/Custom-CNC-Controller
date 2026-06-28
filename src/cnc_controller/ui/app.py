from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from cnc_controller.launchers import ApplicationLaunchError, BcncLauncher
from cnc_controller.models import MachineMode


class TouchControllerApp(tk.Tk):
    def __init__(self, bcnc_launcher: BcncLauncher | None = None) -> None:
        super().__init__()
        self.bcnc_launcher = bcnc_launcher or BcncLauncher()
        self.title("Custom CNC Controller")
        self.geometry("1024x600")
        self.configure(bg="#101820")
        self._build_home()

    def _build_home(self) -> None:
        title = ttk.Label(self, text="Custom CNC Controller", font=("Helvetica", 28, "bold"))
        title.pack(pady=20)
        grid = ttk.Frame(self)
        grid.pack(expand=True)
        buttons = [
            ("CNC Mode", self._launch_bcnc),
            ("Laser Mode", lambda: self._show_mode(MachineMode.LASER)),
            ("PCB Wizard", lambda: self._show_mode(MachineMode.PCB)),
            ("Files", lambda: self._show_panel("Files")),
            ("Settings", lambda: self._show_panel("Settings")),
            ("Shutdown", self.destroy),
        ]
        for index, (label, command) in enumerate(buttons):
            ttk.Button(grid, text=label, command=command, width=24).grid(row=index // 2, column=index % 2, padx=18, pady=14, ipady=18)

    def _launch_bcnc(self) -> None:
        try:
            self.bcnc_launcher.launch()
        except ApplicationLaunchError as exc:
            messagebox.showerror(
                "Unable to start bCNC",
                f"{exc}\n\nInstall it with:\npython -m pip install bCNC",
                parent=self,
            )

    def _show_mode(self, mode: MachineMode) -> None:
        self._show_panel(f"{mode.value.upper()} mode")

    def _show_panel(self, name: str) -> None:
        panel = tk.Toplevel(self)
        panel.title(name)
        panel.geometry("1024x600")
        ttk.Label(panel, text=name, font=("Helvetica", 26, "bold")).pack(pady=20)
        ttk.Label(panel, text="Workflow scaffold ready for GRBL integration.").pack(pady=12)
        ttk.Button(panel, text="Back", command=panel.destroy).pack(pady=20, ipady=12)


def main() -> None:
    TouchControllerApp().mainloop()


if __name__ == "__main__":
    main()
