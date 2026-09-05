"""Keep terminal geometry and scrollback stable as the dock changes size."""

from __future__ import annotations

import pytest

from qtpy.QtCore import Qt

pytestmark = [pytest.mark.qt, pytest.mark.phase3]


def javascript(qtbot, terminal, source):
    result = []
    terminal._view.page().runJavaScript(source, result.append)
    qtbot.waitUntil(lambda: bool(result), timeout=5000)
    return result[0]


def test_long_directory_keeps_session_status_visible(qtbot, terminal):
    terminal.setAttribute(Qt.WA_DontShowOnScreen)
    terminal.resize(400, 300)
    terminal.show()
    path = "C:/" + "nested-project/" * 30 + "analysis"
    terminal.set_working_directory(path)
    qtbot.waitUntil(lambda: terminal._directory_label.width() > 0)
    label = terminal._directory_label
    assert label.toolTip() == path
    assert label.text().endswith("analysis")
    assert len(label.text()) < len(path)
    assert terminal.get_state_label().isVisible()
    assert terminal.width() == 400

    font = label.font()
    font.setPointSize(font.pointSize() + 4)
    label.setFont(font)
    qtbot.waitUntil(lambda: label.fontMetrics().horizontalAdvance(label.text())
                   <= label.contentsRect().width())
    assert label.text().endswith("analysis")


def test_xterm_resize_and_output_preserve_manual_scroll(qtbot, terminal, patched_backend):
    terminal.setAttribute(Qt.WA_DontShowOnScreen)
    terminal.resize(640, 400)
    terminal.show()
    qtbot.waitUntil(lambda: terminal._page_ready, timeout=10000)
    terminal.start_session(provider="none")
    qtbot.waitUntil(lambda: bool(patched_backend.sizes), timeout=5000)
    old_cols = terminal._cols
    terminal.resize(480, 400)
    qtbot.waitUntil(lambda: terminal._cols < old_cols, timeout=5000)
    # One dock resize can schedule more than one fit, so the page may report a
    # geometry the PTY has not received yet. Wait for both to agree instead of
    # sampling the first size that arrives.
    qtbot.waitUntil(lambda: javascript(
        qtbot, terminal, "[aiTerminal.term.rows, aiTerminal.term.cols]"
    ) == [terminal._rows, terminal._cols], timeout=5000)
    assert terminal._cols < old_cols
    assert patched_backend.sizes[-1] == (terminal._rows, terminal._cols)

    patched_backend.sig_output.emit(("history line\r\n" * 100).encode())
    qtbot.waitUntil(lambda: javascript(
        qtbot, terminal, "aiTerminal.term.buffer.active.baseY > 50"
    ), timeout=5000)
    javascript(qtbot, terminal, "aiTerminal.term.scrollToTop()")
    patched_backend.sig_output.emit(b"latest line\r\n")
    qtbot.waitUntil(lambda: javascript(
        qtbot, terminal,
        "aiTerminal.term.buffer.active.getLine("
        "aiTerminal.term.buffer.active.baseY + aiTerminal.term.buffer.active.cursorY - 1)"
        ".translateToString(true) === 'latest line'"
    ), timeout=5000)
    assert javascript(qtbot, terminal, "aiTerminal.term.buffer.active.viewportY") == 0


@pytest.mark.parametrize("palette_name", ["DarkPalette", "LightPalette"])
def test_terminal_selection_has_readable_contrast(widget_module, monkeypatch, palette_name):
    from qdarkstyle.dark.palette import DarkPalette
    from qdarkstyle.light.palette import LightPalette
    from spyder.utils import palette

    selected = {"DarkPalette": DarkPalette, "LightPalette": LightPalette}[palette_name]
    monkeypatch.setattr(palette, "QStylePalette", selected)
    theme = widget_module.terminal_appearance(5000)["theme"]

    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        channels = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                    for c in channels]
        return sum(c * weight for c, weight in zip(channels, (0.2126, 0.7152, 0.0722)))

    levels = sorted(luminance(theme[key]) for key in (
        "selectionBackground", "selectionForeground"
    ))
    assert (levels[1] + 0.05) / (levels[0] + 0.05) >= 4.5
