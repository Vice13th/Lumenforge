# SPDX-License-Identifier: MIT
"""
Accessibility regression tests for the LumenForge UI shell.

Token tests are pure (no display). Widget tests need a display
(Windows/macOS desktop, or ``xvfb-run -a pytest`` on Linux) and are skipped
automatically when Tk cannot open one.
"""
import importlib.util
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "source", "lumenforge.py")


@pytest.fixture(scope="module")
def lf():
    spec = importlib.util.spec_from_file_location("lumenforge_a11y", _SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


SURFACES = ("bg", "panel", "card", "glass")


# ---------------------------------------------------------------- tokens
@pytest.mark.parametrize("fg", ["text", "text_dim", "accent_fg", "gold",
                                "green", "red"])
@pytest.mark.parametrize("bg", SURFACES)
def test_text_tokens_meet_aa_on_surfaces(lf, fg, bg):
    assert lf.contrast(lf.T[fg], lf.T[bg]) >= 4.5


@pytest.mark.parametrize("fg", ["text", "text_dim", "accent_fg"])
def test_text_tokens_meet_aa_on_raised_card(lf, fg):
    assert lf.contrast(lf.T[fg], lf.T["card_hi"]) >= 4.5


@pytest.mark.parametrize("fill", ["accent", "accent2"])
def test_on_accent_text_is_legible_on_solid_fills(lf, fill):
    assert lf.contrast(lf.T["on_accent"], lf.T[fill]) >= 4.5


@pytest.mark.parametrize("bg", ("bg", "panel", "card"))
def test_control_stroke_and_focus_ring_meet_3_to_1(lf, bg):
    assert lf.contrast(lf.T["stroke_ui"], lf.T[bg]) >= 3.0
    assert lf.contrast(lf.T["focus"], lf.T[bg]) >= 3.0


def test_focus_ring_visible_against_solid_accent(lf):
    assert lf.contrast(lf.T["focus"], lf.T["accent"]) >= 3.0


def test_legible_lightens_only_when_needed(lf):
    assert lf.legible("#f3eef1", "#181119") == "#f3eef1"
    out = lf.legible(lf.T["accent"], lf.T["card"])
    assert lf.contrast(out, lf.T["card"]) >= 4.5


def test_ink_on_picks_readable_ink(lf):
    for fill in (lf.T["accent"], lf.T["accent2"], lf.T["red"], "#ffffff",
                 lf.T["gold"], lf.T["green"]):
        assert lf.contrast(lf.ink_on(fill), fill) >= 4.5


# --------------------------------------------------------------- widgets
@pytest.fixture(scope="module")
def tkroot(lf):
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip("no display: %s" % e)
    root.geometry("+0+0")
    root.update()
    yield root
    root.destroy()


def test_btn_is_keyboard_operable(lf, tkroot):
    hits = []
    b = lf.Btn(tkroot, "Probe", lambda: hits.append(1), w=80)
    b.pack()
    tkroot.update()
    assert str(b.cget("takefocus")) == "1"
    b.focus_force()
    tkroot.update()
    b.event_generate("<space>")
    b.event_generate("<Return>")
    tkroot.update()
    assert len(hits) == 2
    b.destroy()


def test_disabled_btn_leaves_tab_order(lf, tkroot):
    b = lf.Btn(tkroot, "Probe", lambda: None, w=80)
    b.pack()
    b.set_en(False)
    tkroot.update()
    assert str(b.cget("takefocus")) == "0"
    b.set_en(True)
    assert str(b.cget("takefocus")) == "1"
    b.destroy()


def test_btn_width_never_smaller_than_its_label(lf, tkroot):
    b = lf.Btn(tkroot, "A fairly long button label", None, w=60,
               icon=lf.ICON["open"])
    assert int(b["width"]) >= b.need_w() > 60
    b.set_compact(True)
    assert int(b["width"]) < b.need_w()
    b.destroy()


def test_slider_keyboard_edit_reset_and_validation(lf, tkroot):
    import tkinter as tk
    var = tk.DoubleVar(value=0.5)
    p = lf.Param(tkroot, "Probe", var, lambda k: None, lo=-1, hi=1,
                 fmt="{:+.2f}", default=0.0)
    p.pack(fill="x")
    tkroot.update()
    p._s.focus_force()
    tkroot.update()
    p._s.event_generate("<Delete>")
    tkroot.update()
    assert var.get() == pytest.approx(0.0)
    p._s.event_generate("<F2>")
    tkroot.update()
    assert p._e is not None
    p._e.delete(0, "end")
    p._e.insert(0, "abc")
    p._e.event_generate("<Return>")
    tkroot.update()
    assert p._e is not None, "invalid input must keep the editor open"
    p._e.delete(0, "end")
    p._e.insert(0, "0.25")
    p._e.event_generate("<Return>")
    tkroot.update()
    assert p._e is None and var.get() == pytest.approx(0.25)
    p.destroy()


def test_slider_focus_ring_uses_focus_token(lf, tkroot):
    import tkinter as tk
    p = lf.Param(tkroot, "Probe", tk.DoubleVar(value=0.0), lambda k: None,
                 lo=-1, hi=1, default=0.0)
    p.pack(fill="x")
    tkroot.update()
    assert p._sf.cget("bg") == lf.T["card"]
    p._s.focus_force()
    tkroot.update()
    assert p._sf.cget("bg") == lf.T["focus"]
    tkroot.focus_force()
    tkroot.update()
    p._s.event_generate("<FocusOut>")
    tkroot.update()
    assert p._sf.cget("bg") == lf.T["card"]
    p.destroy()


def test_curve_editor_keyboard_model(lf, tkroot):
    changes = []
    c = lf._CurveCanvas(tkroot, changes.append)
    c.pack(fill="x")
    tkroot.update()
    c.focus_force()
    tkroot.update()
    n0 = len(c.pts)
    c.event_generate("<Insert>")
    tkroot.update()
    assert len(c.pts) == n0 + 1
    y0 = c.pts[c._sel][1]
    c.event_generate("<Up>")
    tkroot.update()
    assert c.pts[c._sel][1] > y0
    c.event_generate("<Delete>")
    tkroot.update()
    assert len(c.pts) == n0
    assert changes, "keyboard edits must notify the render pipeline"
    c.destroy()


def test_dialog_keyboard_contract(lf, tkroot):
    ran = []
    d = lf.Dlg(tkroot, "Probe", ["x"],
               [("OK", lambda: ran.append(1), True), ("Cancel", None, False)])
    tkroot.update()
    assert tkroot.focus_get() is d._btns[0]
    d.event_generate("<Return>")
    tkroot.update()
    assert ran and not d.winfo_exists()
    d2 = lf.Dlg(tkroot, "Probe", ["x"], [("OK", lambda: None, True)])
    tkroot.update()
    d2.event_generate("<Escape>")
    tkroot.update()
    assert not d2.winfo_exists()
