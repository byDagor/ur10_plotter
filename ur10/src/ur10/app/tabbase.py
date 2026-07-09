"""Common tab plumbing: uniform sidebar + preview relayout."""

import time

import dearpygui.dearpygui as dpg

from .theme import SIDEBAR_W, MARGIN_W


class BaseTab:
    name = ""
    sidebar_tag = ""
    preview_tag = ""
    log_tag = ""
    inner_offset = 12       # vertical space taken by preview chrome (tab strip)

    def __init__(self):
        self.canvases = []

    def log(self, msg):
        stamp = time.strftime("%H:%M:%S")
        if self.log_tag and dpg.does_item_exist(self.log_tag):
            dpg.add_text(f"[{stamp}] {msg}", parent=self.log_tag, wrap=SIDEBAR_W - 60)
            dpg.set_y_scroll(self.log_tag, -1.0)
        print(f"[{self.name}] {msg}")

    def relayout(self, content_w, content_h):
        cw = max(content_w - SIDEBAR_W - MARGIN_W, 220)
        ch = max(content_h - self.inner_offset, 160)
        if dpg.does_item_exist(self.sidebar_tag):
            dpg.configure_item(self.sidebar_tag, height=content_h)
        if dpg.does_item_exist(self.preview_tag):
            dpg.configure_item(self.preview_tag, height=content_h)
        for c in self.canvases:
            c.resize(cw, ch)

    def on_frame(self):
        """Optional per-frame hook (overridden where needed)."""
