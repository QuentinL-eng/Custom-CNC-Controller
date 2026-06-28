"""PCB wizard screen — guided Gerber → isolation → drill → cutout workflow.

Multi-step flow:
  1. Import  — pick Copper Gerber (required), Drill/Excellon (required),
               optional Cutout file.
  2. Generate — call cnc_controller.pcb.generate_pcb_jobs(...) -> list[PcbStage].
  3. Preview  — textual summary of the stages and their flags.
  4. Run      — stream each stage's gcode via controller.worker.start_job(...),
               pausing for tool-change / Z re-probe prompts between stages.
               X/Y work zero is preserved across stages (never re-zeroed).
"""
from __future__ import annotations

from pathlib import Path

from ..qt_compat import (
    Qt, QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QFileDialog,
)
from ..theme import (
    C_CARD, C_CARD_BORDER, C_DIVIDER, C_TEXT, C_MUTED, C_DIM,
    C_GREEN, C_GREEN_BG, C_GREEN_BORDER, C_GREEN_TEXT,
    C_AMBER, C_AMBER_BG, C_AMBER_BORDER, C_AMBER_TEXT,
    C_BLUE, C_BLUE_BG, C_BLUE_BORDER, C_BLUE_TEXT,
    C_RED, C_RED_BG, C_RED_BORDER, C_BTN_2ND,
    CARD_RADIUS, BTN_RADIUS,
)


# ---------------------------------------------------------------------------
# Pure run-plan helper (no Qt) — testable in isolation
# ---------------------------------------------------------------------------

# Prompt kinds the run plan yields before a stage is streamed.
PROMPT_NONE = "none"          # stage can start immediately
PROMPT_TOOL_CHANGE = "tool"   # operator must insert a tool, then continue
PROMPT_PROBE_Z = "probe"      # operator must re-probe Z, then continue


class PcbRunPlan:
    """Drives ordered execution of a list of PCB stages.

    A "stage" is any object exposing the PcbStage contract attributes:
        name, gcode_lines, requires_tool_change, requires_probe_z, description

    Usage:
        plan = PcbRunPlan(stages)
        prompt, stage = plan.next_prompt()   # what to do before stage N
        ...show prompt, get user confirmation...
        plan.confirm()                       # clears the prompt for current stage
        lines = plan.gcode_for_current()     # stream these
        ...on job finished...
        plan.advance()                       # move to next stage

    The plan is intentionally side-effect free: it does NOT talk to the
    worker. The screen wires those bits together. This keeps the ordering
    logic unit-testable without a display or serial port.
    """

    def __init__(self, stages):
        self._stages = list(stages)
        self._index = 0
        self._confirmed = False

    @property
    def total(self) -> int:
        return len(self._stages)

    @property
    def index(self) -> int:
        return self._index

    @property
    def finished(self) -> bool:
        return self._index >= len(self._stages)

    @property
    def current(self):
        if self.finished:
            return None
        return self._stages[self._index]

    def prompt_for(self, stage) -> str:
        """Return the prompt kind required before *stage* may run."""
        if getattr(stage, "requires_tool_change", False):
            return PROMPT_TOOL_CHANGE
        if getattr(stage, "requires_probe_z", False):
            return PROMPT_PROBE_Z
        return PROMPT_NONE

    def next_prompt(self):
        """Return (prompt_kind, stage) for the current stage.

        The first stage never requires an interruption prompt (no tool is
        loaded yet differently from the start), but if it declares a flag we
        still surface it. Returns (PROMPT_NONE, None) when finished.
        """
        stage = self.current
        if stage is None:
            return (PROMPT_NONE, None)
        if self._confirmed:
            return (PROMPT_NONE, stage)
        return (self.prompt_for(stage), stage)

    def confirm(self) -> None:
        """Operator acknowledged the prompt for the current stage."""
        self._confirmed = True

    def gcode_for_current(self) -> list[str]:
        stage = self.current
        if stage is None:
            return []
        return list(getattr(stage, "gcode_lines", []))

    def advance(self) -> None:
        """Mark the current stage done and move to the next."""
        self._index += 1
        self._confirmed = False

    def prompt_sequence(self):
        """Return the ordered list of (prompt_kind, stage_name) prompts.

        Pure inspection helper used by tests and the preview summary; does
        not mutate state.
        """
        out = []
        for stage in self._stages:
            out.append((self.prompt_for(stage), getattr(stage, "name", "")))
        return out


def tool_change_text(stage) -> str:
    """Human prompt for a tool-change interruption before *stage*."""
    name = getattr(stage, "name", "next stage")
    return f"Insert the tool for “{name}”, then press Continue."


def probe_z_text(stage) -> str:
    """Human prompt for a Z re-probe interruption before *stage*."""
    name = getattr(stage, "name", "next stage")
    return (
        f"Re-probe Z for “{name}” (tool length changed). "
        f"Run the Z probe, then press Continue. X/Y zero is preserved."
    )


# ---------------------------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------------------------

def _hdiv(parent: QWidget) -> QFrame:
    f = QFrame(parent)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {C_DIVIDER}; border: none;")
    return f


def _flag_chip(text: str, color: str, bg: str, border: str, parent: QWidget) -> QLabel:
    chip = QLabel(text, parent)
    chip.setStyleSheet(
        f"color: {color}; background: {bg}; border: 1px solid {border}; "
        f"border-radius: 6px; font-size: 11px; font-weight: 700; padding: 3px 8px;"
    )
    return chip


class FilePickRow(QFrame):
    """A row with a label, the chosen filename, and a Choose button."""

    def __init__(self, title: str, optional: bool, on_pick,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        self._on_pick = on_pick
        self.path: Path | None = None

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(14, 12, 14, 12)
        lyt.setSpacing(12)

        text_w = QWidget(self)
        text_w.setStyleSheet("background: transparent; border: none;")
        tl = QVBoxLayout(text_w)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(2)

        label = title + ("  (optional)" if optional else "")
        t = QLabel(label, text_w)
        t.setStyleSheet(
            f"color: {C_TEXT}; font-size: 15px; font-weight: 700; background: transparent; border: none;"
        )
        self._name = QLabel("No file chosen", text_w)
        self._name.setStyleSheet(
            f"color: {C_DIM}; font-size: 12px; background: transparent; border: none;"
        )
        tl.addWidget(t)
        tl.addWidget(self._name)
        lyt.addWidget(text_w, 1)

        btn = QPushButton("Choose…", self)
        btn.setObjectName("btnSecondary")
        btn.setFixedHeight(46)
        btn.clicked.connect(self._on_pick)
        lyt.addWidget(btn)

    def set_path(self, path: Path | None) -> None:
        self.path = path
        if path is None:
            self._name.setText("No file chosen")
            self._name.setStyleSheet(
                f"color: {C_DIM}; font-size: 12px; background: transparent; border: none;"
            )
        else:
            self._name.setText(path.name)
            self._name.setStyleSheet(
                f"color: {C_GREEN}; font-size: 12px; font-weight: 700; background: transparent; border: none;"
            )


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------

STEP_IMPORT = 0
STEP_GENERATE = 1
STEP_PREVIEW = 2
STEP_RUN = 3

STEP_TITLES = ["Import", "Generate", "Preview", "Run"]


class PcbWizardScreen(QWidget):
    """Guided PCB milling workflow screen."""

    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctrl = controller
        self._step = STEP_IMPORT

        self._copper: Path | None = None
        self._drill: Path | None = None
        self._cutout: Path | None = None

        self._stages: list = []
        self._plan: PcbRunPlan | None = None
        self._running = False

        self._build_ui()
        self._show_step(STEP_IMPORT)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(11)

        # Stepper header
        self._stepper = QHBoxLayout()
        self._stepper.setSpacing(8)
        self._step_chips: list[QLabel] = []
        for i, title in enumerate(STEP_TITLES):
            chip = QLabel(f"{i + 1}. {title}", self)
            chip.setAlignment(Qt.AlignCenter)
            chip.setFixedHeight(34)
            self._step_chips.append(chip)
            self._stepper.addWidget(chip, 1)
        root.addLayout(self._stepper)

        # Body card holds the active step's content
        body = QFrame(self)
        body.setObjectName("card")
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(16, 16, 16, 16)
        body_l.setSpacing(11)

        self._step_title = QLabel("", body)
        self._step_title.setObjectName("labelTitle")
        body_l.addWidget(self._step_title)

        self._step_hint = QLabel("", body)
        self._step_hint.setWordWrap(True)
        self._step_hint.setStyleSheet(
            f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;"
        )
        body_l.addWidget(self._step_hint)

        # Scrollable content region (stages list / file rows / preview)
        scroll = QScrollArea(body)
        scroll.setWidgetResizable(True)
        self._content = QWidget(scroll)
        self._content_l = QVBoxLayout(self._content)
        self._content_l.setContentsMargins(0, 0, 0, 0)
        self._content_l.setSpacing(9)
        self._content_l.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._content)
        body_l.addWidget(scroll, 1)

        root.addWidget(body, 1)

        # Footer: status line + nav buttons
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self._status_lbl = QLabel("", self)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet(
            f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;"
        )
        footer.addWidget(self._status_lbl, 1)

        self._back_btn = QPushButton("Back", self)
        self._back_btn.setObjectName("btnSecondary")
        self._back_btn.setFixedHeight(54)
        self._back_btn.clicked.connect(self._on_back)
        footer.addWidget(self._back_btn)

        # Secondary action (e.g. "Continue" during a run pause)
        self._action_btn = QPushButton("", self)
        self._action_btn.setObjectName("btnWarning")
        self._action_btn.setFixedHeight(54)
        self._action_btn.clicked.connect(self._on_action)
        self._action_btn.setVisible(False)
        footer.addWidget(self._action_btn)

        # Primary forward button
        self._next_btn = QPushButton("Next", self)
        self._next_btn.setObjectName("btnPrimary")
        self._next_btn.setFixedHeight(54)
        self._next_btn.setMinimumWidth(150)
        self._next_btn.clicked.connect(self._on_next)
        footer.addWidget(self._next_btn)

        root.addLayout(footer)

    # ------------------------------------------------------------------
    # Step navigation
    # ------------------------------------------------------------------

    def _clear_content(self) -> None:
        while self._content_l.count():
            item = self._content_l.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _show_step(self, step: int) -> None:
        self._step = step
        self._update_stepper()
        self._clear_content()
        self._action_btn.setVisible(False)
        self._status_lbl.setText("")
        self._back_btn.setEnabled(step != STEP_IMPORT)

        self._step_title.setText(STEP_TITLES[step])

        if step == STEP_IMPORT:
            self._build_import_step()
        elif step == STEP_GENERATE:
            self._build_generate_step()
        elif step == STEP_PREVIEW:
            self._build_preview_step()
        elif step == STEP_RUN:
            self._build_run_step()

    def _update_stepper(self) -> None:
        for i, chip in enumerate(self._step_chips):
            if i == self._step:
                chip.setStyleSheet(
                    f"color: white; background: {C_GREEN}; border: 1px solid {C_GREEN}; "
                    f"border-radius: 8px; font-size: 13px; font-weight: 700;"
                )
            elif i < self._step:
                chip.setStyleSheet(
                    f"color: {C_GREEN_TEXT}; background: {C_GREEN_BG}; "
                    f"border: 1px solid {C_GREEN_BORDER}; border-radius: 8px; "
                    f"font-size: 13px; font-weight: 700;"
                )
            else:
                chip.setStyleSheet(
                    f"color: {C_DIM}; background: {C_BTN_2ND}; border: 1px solid {C_CARD_BORDER}; "
                    f"border-radius: 8px; font-size: 13px; font-weight: 600;"
                )

    # ------------------------------------------------------------------
    # Step 1: Import
    # ------------------------------------------------------------------

    def _build_import_step(self) -> None:
        self._step_hint.setText(
            "Choose the Gerber and drill files exported from your PCB CAD. "
            "Copper isolation and drill files are required; cutout is optional."
        )

        self._copper_row = FilePickRow(
            "Copper Gerber", optional=False,
            on_pick=lambda: self._pick("copper"), parent=self._content,
        )
        self._copper_row.set_path(self._copper)
        self._content_l.addWidget(self._copper_row)

        self._drill_row = FilePickRow(
            "Drill / Excellon", optional=False,
            on_pick=lambda: self._pick("drill"), parent=self._content,
        )
        self._drill_row.set_path(self._drill)
        self._content_l.addWidget(self._drill_row)

        self._cutout_row = FilePickRow(
            "Board Cutout", optional=True,
            on_pick=lambda: self._pick("cutout"), parent=self._content,
        )
        self._cutout_row.set_path(self._cutout)
        self._content_l.addWidget(self._cutout_row)

        self._next_btn.setText("Generate →")
        self._next_btn.setVisible(True)
        self._refresh_import_next()

    def _pick(self, which: str) -> None:
        filt = "Gerber / Drill (*.gbr *.gtl *.gbl *.drl *.xln *.txt *.nc);;All files (*)"
        result = QFileDialog.getOpenFileName(self, "Select file", "", filt)
        # PySide6/PyQt5 both return (path, filter)
        path_str = result[0] if isinstance(result, (tuple, list)) else result
        if not path_str:
            return
        path = Path(path_str)
        if which == "copper":
            self._copper = path
            self._copper_row.set_path(path)
        elif which == "drill":
            self._drill = path
            self._drill_row.set_path(path)
        elif which == "cutout":
            self._cutout = path
            self._cutout_row.set_path(path)
        self._refresh_import_next()

    def _refresh_import_next(self) -> None:
        ready = self._copper is not None and self._drill is not None
        self._next_btn.setEnabled(ready)
        if not ready:
            self._status_lbl.setText("Copper Gerber and Drill files are required.")
        else:
            self._status_lbl.setText("")

    # ------------------------------------------------------------------
    # Step 2: Generate
    # ------------------------------------------------------------------

    def _build_generate_step(self) -> None:
        self._step_hint.setText(
            "Parsing Gerber/Excellon and generating isolation, drill, and "
            "cutout toolpaths for the active machine profile."
        )
        self._next_btn.setText("Preview →")
        self._next_btn.setVisible(True)
        self._next_btn.setEnabled(False)

        self._generate_jobs()

    def _generate_jobs(self) -> None:
        self._stages = []
        try:
            from ...pcb import generate_pcb_jobs
        except Exception as exc:  # backend not available
            self._show_generate_error(f"PCB backend unavailable: {exc}")
            return

        try:
            stages = generate_pcb_jobs(
                self._copper, self._drill, self._cutout, self._ctrl.profile
            )
        except Exception as exc:  # parsing / generation failure
            self._show_generate_error(f"Could not generate toolpaths: {exc}")
            return

        self._stages = list(stages or [])
        if not self._stages:
            self._show_generate_error("No toolpaths were produced from these files.")
            return

        # Render the produced stage list.
        for i, stage in enumerate(self._stages):
            self._content_l.addWidget(self._stage_card(i, stage))

        self._status_lbl.setText(
            f"{len(self._stages)} stage(s) generated."
        )
        self._next_btn.setEnabled(True)

    def _show_generate_error(self, message: str) -> None:
        card = QFrame(self._content)
        card.setStyleSheet(
            f"QFrame {{ background: {C_RED_BG}; border: 1px solid {C_RED_BORDER}; "
            f"border-radius: {CARD_RADIUS}px; }}"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 14, 14, 14)
        cl.setSpacing(4)
        t = QLabel("Generation failed", card)
        t.setStyleSheet(
            f"color: {C_RED}; font-size: 15px; font-weight: 700; background: transparent; border: none;"
        )
        d = QLabel(message, card)
        d.setWordWrap(True)
        d.setStyleSheet(
            f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;"
        )
        cl.addWidget(t)
        cl.addWidget(d)
        self._content_l.addWidget(card)
        self._status_lbl.setText("Go Back to re-pick files, or check the backend.")
        self._next_btn.setEnabled(False)

    def _stage_card(self, idx: int, stage) -> QFrame:
        card = QFrame(self._content)
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(7)

        head = QHBoxLayout()
        head.setSpacing(8)
        name = getattr(stage, "name", f"Stage {idx + 1}")
        t = QLabel(f"{idx + 1}.  {name}", card)
        t.setStyleSheet(
            f"color: {C_TEXT}; font-size: 16px; font-weight: 700; background: transparent; border: none;"
        )
        head.addWidget(t)
        head.addStretch()

        n_lines = len(getattr(stage, "gcode_lines", []) or [])
        count = QLabel(f"{n_lines} lines", card)
        count.setStyleSheet(
            f"color: {C_DIM}; font-size: 12px; background: transparent; border: none;"
        )
        head.addWidget(count)
        cl.addLayout(head)

        desc = getattr(stage, "description", "")
        if desc:
            d = QLabel(desc, card)
            d.setWordWrap(True)
            d.setStyleSheet(
                f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;"
            )
            cl.addWidget(d)

        flags = QHBoxLayout()
        flags.setSpacing(7)
        if getattr(stage, "requires_tool_change", False):
            flags.addWidget(_flag_chip(
                "TOOL CHANGE", C_AMBER_TEXT, C_AMBER_BG, C_AMBER_BORDER, card
            ))
        if getattr(stage, "requires_probe_z", False):
            flags.addWidget(_flag_chip(
                "PROBE Z", C_BLUE_TEXT, C_BLUE_BG, C_BLUE_BORDER, card
            ))
        flags.addStretch()
        cl.addLayout(flags)
        return card

    # ------------------------------------------------------------------
    # Step 3: Preview
    # ------------------------------------------------------------------

    def _build_preview_step(self) -> None:
        self._step_hint.setText(
            "Review the full sequence before running. Tool-change and Z re-probe "
            "pauses are inserted automatically; X/Y work zero is preserved throughout."
        )
        self._next_btn.setText("Start Run →")
        self._next_btn.setVisible(True)

        if not self._stages:
            self._status_lbl.setText("No stages to preview.")
            self._next_btn.setEnabled(False)
            return

        plan = PcbRunPlan(self._stages)
        total_lines = sum(len(getattr(s, "gcode_lines", []) or []) for s in self._stages)
        tool_changes = sum(1 for s in self._stages if getattr(s, "requires_tool_change", False))
        probes = sum(1 for s in self._stages if getattr(s, "requires_probe_z", False))

        # Summary card
        summary = QFrame(self._content)
        summary.setObjectName("card")
        sl = QVBoxLayout(summary)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.setSpacing(0)
        sl.addWidget(self._kv("Stages", str(len(self._stages))))
        sl.addWidget(_hdiv(summary))
        sl.addWidget(self._kv("Total G-code lines", str(total_lines)))
        sl.addWidget(_hdiv(summary))
        sl.addWidget(self._kv("Tool changes", str(tool_changes)))
        sl.addWidget(_hdiv(summary))
        sl.addWidget(self._kv("Z re-probes", str(probes)))
        self._content_l.addWidget(summary)

        # Ordered sequence with prompts
        seq = QFrame(self._content)
        seq.setObjectName("card")
        ql = QVBoxLayout(seq)
        ql.setContentsMargins(14, 12, 14, 12)
        ql.setSpacing(6)
        seq_title = QLabel("SEQUENCE", seq)
        seq_title.setObjectName("labelSection")
        ql.addWidget(seq_title)
        for prompt, name in plan.prompt_sequence():
            line = name
            if prompt == PROMPT_TOOL_CHANGE:
                line += "   (pause: tool change)"
            elif prompt == PROMPT_PROBE_Z:
                line += "   (pause: re-probe Z)"
            row = QLabel("•  " + line, seq)
            row.setStyleSheet(
                f"color: {C_TEXT}; font-size: 13px; background: transparent; border: none;"
            )
            ql.addWidget(row)
        self._content_l.addWidget(seq)

        # TODO: render real geometry preview of the toolpaths.
        self._next_btn.setEnabled(True)
        self._status_lbl.setText("")

    def _kv(self, key: str, val: str) -> QFrame:
        f = QFrame(self._content)
        f.setStyleSheet("background: transparent; border: none;")
        rl = QHBoxLayout(f)
        rl.setContentsMargins(0, 6, 0, 6)
        k = QLabel(key, f)
        k.setStyleSheet(f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;")
        v = QLabel(val, f)
        v.setStyleSheet(
            f"color: {C_TEXT}; font-size: 14px; font-weight: 700; background: transparent; border: none;"
        )
        rl.addWidget(k)
        rl.addStretch()
        rl.addWidget(v)
        return f

    # ------------------------------------------------------------------
    # Step 4: Run
    # ------------------------------------------------------------------

    def _build_run_step(self) -> None:
        self._step_hint.setText(
            "Executing stages in order. Follow on-screen prompts between stages."
        )
        self._plan = PcbRunPlan(self._stages)
        self._running = True
        self._next_btn.setVisible(False)
        self._back_btn.setEnabled(False)

        self._run_status = QLabel("", self._content)
        self._run_status.setWordWrap(True)
        self._run_status.setStyleSheet(
            f"color: {C_TEXT}; font-size: 15px; font-weight: 700; background: transparent; border: none;"
        )
        self._content_l.addWidget(self._run_status)

        self._run_detail = QLabel("", self._content)
        self._run_detail.setWordWrap(True)
        self._run_detail.setStyleSheet(
            f"color: {C_MUTED}; font-size: 13px; background: transparent; border: none;"
        )
        self._content_l.addWidget(self._run_detail)

        self._prepare_current_stage()

    def _prepare_current_stage(self) -> None:
        """Either prompt for an interruption or start the current stage."""
        plan = self._plan
        if plan is None:
            return
        if plan.finished:
            self._on_run_complete()
            return

        prompt, stage = plan.next_prompt()
        n = plan.index + 1
        self._run_status.setText(f"Stage {n} / {plan.total}: {getattr(stage, 'name', '')}")

        if prompt == PROMPT_TOOL_CHANGE:
            self._run_detail.setText(tool_change_text(stage))
            self._show_action("Continue")
        elif prompt == PROMPT_PROBE_Z:
            self._run_detail.setText(probe_z_text(stage))
            self._show_action("Continue")
        else:
            self._run_detail.setText(getattr(stage, "description", "") or "Streaming toolpath…")
            self._action_btn.setVisible(False)
            self._stream_current_stage()

    def _show_action(self, label: str) -> None:
        self._action_btn.setText(label)
        self._action_btn.setObjectName("btnWarning")
        self._action_btn.setStyleSheet("")  # let QSS objectName styling apply
        self._action_btn.setVisible(True)
        self._action_btn.setEnabled(True)

    def _on_action(self) -> None:
        """Operator pressed Continue at an interruption prompt."""
        plan = self._plan
        if plan is None:
            return
        prompt, _stage = plan.next_prompt()
        if prompt == PROMPT_PROBE_Z:
            # Acknowledge then stream. The operator may instead navigate to the
            # dedicated probing screen; we surface the option but do not block.
            plan.confirm()
            self._action_btn.setVisible(False)
            self._run_detail.setText("Z re-probe acknowledged. Streaming toolpath…")
            self._stream_current_stage()
        elif prompt == PROMPT_TOOL_CHANGE:
            plan.confirm()
            self._action_btn.setVisible(False)
            self._run_detail.setText("Tool inserted. Streaming toolpath…")
            self._stream_current_stage()

    def _stream_current_stage(self) -> None:
        plan = self._plan
        if plan is None:
            return
        worker = getattr(self._ctrl, "worker", None)
        lines = plan.gcode_for_current()
        if worker is None:
            self._run_detail.setText(
                "No machine connected — cannot stream. Connect GRBL and retry."
            )
            return
        if not lines:
            # Nothing to send; treat as immediately finished.
            self.on_job_finished(True)
            return
        worker.start_job(lines)

    def _on_run_complete(self) -> None:
        self._running = False
        self._run_status.setText("PCB job complete ✓")
        self._run_status.setStyleSheet(
            f"color: {C_GREEN}; font-size: 16px; font-weight: 700; background: transparent; border: none;"
        )
        self._run_detail.setText("All stages finished. You may unload the board.")
        self._action_btn.setVisible(False)
        self._next_btn.setText("Done")
        self._next_btn.setVisible(True)
        self._next_btn.setEnabled(True)
        self._back_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Footer button handlers
    # ------------------------------------------------------------------

    def _on_next(self) -> None:
        if self._step == STEP_IMPORT:
            if self._copper is None or self._drill is None:
                return
            self._show_step(STEP_GENERATE)
        elif self._step == STEP_GENERATE:
            if not self._stages:
                return
            self._show_step(STEP_PREVIEW)
        elif self._step == STEP_PREVIEW:
            self._show_step(STEP_RUN)
        elif self._step == STEP_RUN:
            # "Done"
            self._ctrl.navigate_to("home")

    def _on_back(self) -> None:
        if self._step == STEP_IMPORT:
            return
        if self._step == STEP_RUN and self._running:
            # Abort an in-progress run safely.
            worker = getattr(self._ctrl, "worker", None)
            if worker is not None:
                worker.stop_job()
            self._running = False
        self._show_step(self._step - 1)

    # ------------------------------------------------------------------
    # Controller hooks
    # ------------------------------------------------------------------

    def on_enter(self) -> None:
        self._ctrl.rail.set_enc1("PCB", STEP_TITLES[self._step].lower())
        self._ctrl.rail.set_enc2("—", "idle")

    def on_job_finished(self, success: bool) -> None:
        if not self._running or self._step != STEP_RUN or self._plan is None:
            return
        if not success:
            self._run_status.setText("Stage failed ✕")
            self._run_status.setStyleSheet(
                f"color: {C_RED}; font-size: 16px; font-weight: 700; background: transparent; border: none;"
            )
            self._run_detail.setText(
                "GRBL reported an error. Fix the issue and press Back to retry."
            )
            self._running = False
            self._back_btn.setEnabled(True)
            return
        # Stage succeeded — advance and either prompt or finish.
        self._plan.advance()
        self._prepare_current_stage()

    def on_job_progress(self, cur: int, total: int) -> None:
        if self._step == STEP_RUN and self._running and total:
            self._run_detail.setText(f"Streaming… line {cur} / {total}")
