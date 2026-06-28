"""Tests for the file browser pure helpers (no Qt / display required)."""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest


def _load_helpers():
    """Import file_browser's pure helpers without requiring a Qt backend.

    We stub out the qt_compat, theme, touch_keyboard, grbl_worker and gcode
    imports so the module can be imported headlessly. Only the pure helper
    functions are exercised here.
    """
    src = Path(__file__).resolve().parents[1] / "src"
    mod_path = src / "cnc_controller" / "ui" / "screens" / "file_browser.py"
    source = mod_path.read_text()

    # Build a throwaway namespace that satisfies the module's imports.
    fake_pkg = types.ModuleType("_fb_fakes")

    class _Dummy:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, name):
            return _Dummy()

        def __call__(self, *a, **k):
            return _Dummy()

    ns: dict = {
        "__name__": "file_browser_helpers",
        "__file__": str(mod_path),
        "json": json, "os": os, "sys": sys, "Path": Path,
        "Qt": _Dummy(), "QWidget": _Dummy, "QLabel": _Dummy, "QFrame": _Dummy,
        "QVBoxLayout": _Dummy, "QHBoxLayout": _Dummy, "QPushButton": _Dummy,
        "QScrollArea": _Dummy, "QSizePolicy": _Dummy, "QLineEdit": _Dummy,
        "QTimer": _Dummy, "QEvent": _Dummy(), "QPixmap": _Dummy,
        "QPainter": _Dummy, "QPen": _Dummy, "QColor": _Dummy,
    }
    # Strip the leading import block and exec the rest with our namespace.
    lines = source.splitlines()
    # Find first non-import top-level statement after the import block.
    start = 0
    for i, line in enumerate(lines):
        if line.startswith("EXT_COLORS"):
            start = i
            break
    body = "\n".join(lines[start:])
    # Provide the theme color names referenced as module-level constants.
    for name in ("C_CARD", "C_CARD_BORDER", "C_DIVIDER", "C_TEXT", "C_MUTED",
                 "C_DIM", "C_GREEN", "C_BLUE", "C_AMBER", "C_BTN_2ND", "C_BG",
                 "C_GREEN_BG", "C_BLUE_BG", "C_AMBER_BG"):
        ns[name] = "#000000"
    ns["CARD_RADIUS"] = 12
    ns["BTN_RADIUS"] = 10
    exec(compile(body, str(mod_path), "exec"), ns)
    return types.SimpleNamespace(**ns)


fb = _load_helpers()


# -- matches_filter ----------------------------------------------------------

def test_matches_filter_empty_matches_all():
    assert fb.matches_filter("anything.nc", "") is True
    assert fb.matches_filter("anything.nc", "   ") is True


def test_matches_filter_case_insensitive_substring():
    assert fb.matches_filter("PartABC.gcode", "abc") is True
    assert fb.matches_filter("PartABC.gcode", "xyz") is False


# -- list_directory ----------------------------------------------------------

def test_list_directory_folders_first_and_filters_ext(tmp_path: Path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.nc").write_text("G0\n")
    (tmp_path / "b.txt").write_text("ignore")
    (tmp_path / ".hidden").write_text("x")
    result = fb.list_directory(tmp_path)
    names = [p.name for p in result]
    assert names[0] == "sub"          # directory first
    assert "a.nc" in names            # supported file kept
    assert "b.txt" not in names       # unsupported ext dropped
    assert ".hidden" not in names     # hidden skipped


def test_list_directory_files_newest_first(tmp_path: Path):
    import os
    old = tmp_path / "old.nc"
    new = tmp_path / "new.nc"
    old.write_text("G0\n")
    new.write_text("G0\n")
    os.utime(old, (1000, 1000))
    os.utime(new, (2000, 2000))
    result = fb.list_directory(tmp_path)
    files = [p.name for p in result if p.is_file()]
    assert files == ["new.nc", "old.nc"]


def test_list_directory_cap(tmp_path: Path):
    for i in range(10):
        (tmp_path / f"f{i}.nc").write_text("G0\n")
    result = fb.list_directory(tmp_path, cap=3)
    assert len(result) == 3


def test_list_directory_missing_path_returns_empty(tmp_path: Path):
    assert fb.list_directory(tmp_path / "nope") == []


# -- discover_removable_media ------------------------------------------------

def test_discover_media_linux_media(tmp_path: Path):
    media = tmp_path / "media" / "usb0"
    media.mkdir(parents=True)
    found = fb.discover_removable_media(platform="linux", root=tmp_path)
    assert media in found


def test_discover_media_linux_run_media_user_level(tmp_path: Path):
    mount = tmp_path / "run" / "media" / "quentin" / "STICK"
    mount.mkdir(parents=True)
    found = fb.discover_removable_media(platform="linux", root=tmp_path)
    assert mount in found


def test_discover_media_none_returns_empty(tmp_path: Path):
    found = fb.discover_removable_media(platform="linux", root=tmp_path)
    assert found == []


def test_discover_media_windows_drive_letters(tmp_path: Path):
    # With a test ``root``, drives are probed as bare-letter directories
    # (a colon is a reserved drive specifier on Windows).
    drive = tmp_path / "E"
    drive.mkdir()
    found = fb.discover_removable_media(
        platform="win32", drive_letters="DE", root=tmp_path
    )
    assert drive in found
    assert all(p.name != "D" for p in found)  # D not created


# -- favorites persistence ---------------------------------------------------

def test_favorites_round_trip(tmp_path: Path):
    path = tmp_path / "file_favorites.json"
    fb.save_favorites(path, ["/a/x.nc", "/b/y.gcode"])
    assert fb.load_favorites(path) == ["/a/x.nc", "/b/y.gcode"]


def test_load_favorites_missing_file(tmp_path: Path):
    assert fb.load_favorites(tmp_path / "missing.json") == []


def test_load_favorites_corrupt_file(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json")
    assert fb.load_favorites(path) == []


def test_load_favorites_legacy_list_format(tmp_path: Path):
    path = tmp_path / "legacy.json"
    path.write_text('["/a.nc", "/b.nc"]')
    assert fb.load_favorites(path) == ["/a.nc", "/b.nc"]


def test_save_favorites_creates_parent_dirs(tmp_path: Path):
    path = tmp_path / "nested" / "dir" / "favs.json"
    fb.save_favorites(path, ["/x.nc"])
    assert fb.load_favorites(path) == ["/x.nc"]
