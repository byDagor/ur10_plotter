"""Shared base for the vectorizer tabs (Flow, Hatched, Dither).

Each produces a vpype.Document, previews it on a PreviewCanvas, can optimise it
(linemerge / linesimplify / linesort) and save it. The heavy vectorization runs
off-thread in the existing vectorizer modules, which report back through an
EventBridge (-LOG_MESSAGE- / -THREAD_DONE-).
"""

import threading

import dearpygui.dearpygui as dpg
import vpype
from vpype_cli import execute

from .tabbase import BaseTab
from .bridge import EventBridge
from .canvas import PreviewCanvas, document_to_items
from .dialogs import save_file
from .util import clean_num
from .theme import make_button_theme, C_START, C_STOP


class VectorizerTab(BaseTab):
    prefix = "vec"

    def __init__(self):
        super().__init__()
        self.sidebar_tag = f"{self.prefix}_sidebar"
        self.preview_tag = f"{self.prefix}_preview"
        self.log_tag = f"{self.prefix}_log"
        self.canvas_tag = f"{self.prefix}_canvas"
        self.vec_btn = f"{self.prefix}_btn_vec"
        self.stop_btn = f"{self.prefix}_btn_stop"
        self.merge_tag = f"{self.prefix}_merge"
        self.simplify_tag = f"{self.prefix}_simplify"

        self.document = None
        self.is_cmyk = False
        self.stop_event = threading.Event()
        self.canvas = PreviewCanvas(self.canvas_tag, flip_y=False)
        self.canvases = [self.canvas]
        self.bridge = EventBridge(handlers={
            "-LOG_MESSAGE-": self.log,
            "-THREAD_DONE-": self._on_done,
        })

    # ------------------------------------------------------------------ #
    # Shared layout pieces
    # ------------------------------------------------------------------ #
    def _wrap(self, parent, build_controls):
        with dpg.group(horizontal=True, parent=parent):
            with dpg.child_window(tag=self.sidebar_tag, width=400):
                build_controls()
            with dpg.child_window(tag=self.preview_tag, width=-1, no_scrollbar=True):
                self.canvas.build()

    def _vectorize_buttons(self):
        with dpg.group(horizontal=True):
            dpg.add_button(label="Vectorize", tag=self.vec_btn, width=-110,
                           callback=self.vectorize)
            dpg.add_button(label="Stop", tag=self.stop_btn, width=-1, enabled=False,
                           callback=self.stop)

    def _optimize_and_save(self):
        from .theme import section
        section("Optimization")
        with dpg.group(horizontal=True):
            dpg.add_text("Merge mm")
            dpg.add_input_text(tag=self.merge_tag, default_value="0.1", width=60)
            dpg.add_text("Simplify mm")
            dpg.add_input_text(tag=self.simplify_tag, default_value="0.05", width=60)
        dpg.add_button(label="Optimize Drawing", width=-1, callback=self.optimize)
        dpg.add_button(label="Save SVG", tag=f"{self.prefix}_btn_save", width=-1,
                       callback=self.save)

    def apply_button_themes(self):
        dpg.bind_item_theme(self.vec_btn, make_button_theme(C_START))
        dpg.bind_item_theme(self.stop_btn, make_button_theme(C_STOP))
        dpg.bind_item_theme(f"{self.prefix}_btn_save", make_button_theme(C_START))

    # ------------------------------------------------------------------ #
    # Threading helpers
    # ------------------------------------------------------------------ #
    def _start(self, target, args):
        self.stop_event.clear()
        dpg.configure_item(self.vec_btn, enabled=False)
        dpg.configure_item(self.stop_btn, enabled=True)
        threading.Thread(target=target, args=args, daemon=True).start()

    def stop(self):
        self.stop_event.set()
        dpg.configure_item(self.vec_btn, enabled=True)
        dpg.configure_item(self.stop_btn, enabled=False)
        self.log("Vectorization stopped by user.")

    def _on_done(self, value):
        doc, message, is_cmyk = value
        dpg.configure_item(self.vec_btn, enabled=True)
        dpg.configure_item(self.stop_btn, enabled=False)
        if self.stop_event.is_set():
            return
        if "complete" not in message:
            if "stop" in message.lower():
                self.log(message)
            else:
                self.log(f"Failed: {message}")
            return
        if doc and not doc.is_empty():
            self.is_cmyk = is_cmyk
            self.document = self._transform_document(doc)
            self.render_current()
            self.log(message)
        else:
            self.document = None
            self.canvas.clear()
            self.log("Result was empty.")

    # ------------------------------------------------------------------ #
    # Preview / optimize / save (overridable)
    # ------------------------------------------------------------------ #
    def _transform_document(self, doc):
        """Hook to post-process the received document (identity by default)."""
        return doc

    def render_current(self):
        if not self.document:
            self.canvas.clear()
            return
        items, bounds = document_to_items(self.document, self.is_cmyk)
        self.canvas.set_items(items, bounds)

    def optimize(self):
        if not self.document:
            self.log("Nothing to optimize. Vectorize first.")
            return
        m = clean_num(dpg.get_value(self.merge_tag))
        s = clean_num(dpg.get_value(self.simplify_tag))
        self.log("Optimizing (linemerge / linesimplify / linesort)...")
        doc = execute(f"linemerge -t {m}mm linesimplify -t {s}mm linesort",
                      document=self.document)
        if doc:
            self.document = doc
            self.render_current()
            self.log("Optimization complete.")
        else:
            self.log("Optimization failed.")

    def save(self):
        if not self.document:
            self.log("Nothing to save. Vectorize first.")
            return
        path = save_file(title="Save SVG")
        if not path:
            self.log("Save cancelled.")
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                vpype.write_svg(f, self.document)
            self.log(f"Saved SVG to {path}.")
        except Exception as exc:
            self.log(f"Error saving: {exc}")

    # Subclasses must implement:
    def vectorize(self):
        raise NotImplementedError
