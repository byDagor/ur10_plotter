"""PLOTTUR10 application shell: mode tab bar + render loop."""

import os

import dearpygui.dearpygui as dpg

from . import bridge, canvas
from .theme import build_global_theme

# Tabs
from .tab_ur10 import UR10Tab


def _build_tabs():
    """Order defines the mode tab bar. Vectorizer tabs are appended as ported."""
    tabs = []
    try:
        from .tab_flow import FlowTab
        tabs.append(FlowTab())
    except Exception as exc:                              # pragma: no cover
        print(f"Flow tab unavailable: {exc}")
    try:
        from .tab_hatched import HatchedTab
        tabs.append(HatchedTab())
    except Exception as exc:                              # pragma: no cover
        print(f"Hatched tab unavailable: {exc}")
    try:
        from .tab_dither import DitherTab
        tabs.append(DitherTab())
    except Exception as exc:                              # pragma: no cover
        print(f"Dither tab unavailable: {exc}")
    try:
        from .tab_text import TextTab
        tabs.append(TextTab())
    except Exception as exc:                              # pragma: no cover
        print(f"Text tab unavailable: {exc}")

    tabs.append(UR10Tab())

    try:
        from .tab_instructions import InstructionsTab
        tabs.append(InstructionsTab())
    except Exception as exc:                              # pragma: no cover
        print(f"Instructions tab unavailable: {exc}")
    return tabs


TABS = []


def build_shell():
    with dpg.window(tag="primary", no_scrollbar=True):
        dpg.add_text("PLOTTUR10", color=(236, 238, 242))
        with dpg.tab_bar(tag="mode_tabs"):
            for tab in TABS:
                with dpg.tab(label=tab.name) as tab_id:
                    tab.build(tab_id)
    for tab in TABS:
        if hasattr(tab, "apply_button_themes"):
            tab.apply_button_themes()


def relayout(sender=None, app_data=None):
    vpw = dpg.get_viewport_client_width()
    vph = dpg.get_viewport_client_height()
    content_w = max(vpw - 24, 400)
    content_h = max(vph - 92, 240)
    for tab in TABS:
        tab.relayout(content_w, content_h)


def _frame():
    bridge.pump_all()
    canvas.pump_all()
    for tab in TABS:
        tab.on_frame()


def main():
    global TABS
    smoke = os.environ.get("DPG_SMOKE_TEST") == "1"

    dpg.create_context()
    dpg.create_viewport(title="PLOTTUR10", width=1200, height=840,
                        min_width=980, min_height=640)
    dpg.bind_theme(build_global_theme())

    TABS = _build_tabs()
    build_shell()

    dpg.setup_dearpygui()
    dpg.set_primary_window("primary", True)
    dpg.set_global_font_scale(1.12)
    dpg.set_viewport_resize_callback(relayout)

    dpg.show_viewport()
    relayout()

    # Post-build init hooks
    for tab in TABS:
        if hasattr(tab, "load_home"):
            tab.load_home()

    if smoke:
        for _ in range(8):
            _frame()
            dpg.render_dearpygui_frame()
        print("SMOKE TEST OK: shell built and rendered without errors.")
        dpg.destroy_context()
        return

    while dpg.is_dearpygui_running():
        _frame()
        dpg.render_dearpygui_frame()

    dpg.destroy_context()
