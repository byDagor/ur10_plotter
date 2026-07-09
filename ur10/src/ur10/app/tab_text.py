"""Text tab: lay out single-stroke (Hershey) text and export an SVG."""

import dearpygui.dearpygui as dpg
import vpype
from vpype_cli import execute

from text_object import TextObject

from .tabbase import BaseTab
from .bridge import EventBridge  # noqa: F401 (kept for parity; text runs inline)
from .canvas import PreviewCanvas, document_to_items
from .dialogs import save_file
from .theme import section, make_button_theme, C_START

FONTS = ["futural", "Hershey", "astrology", "cursive", "cyrillic", "futuram", "gothgbt",
         "gothgrt", "gothiceng", "gothicger", "gothicita", "gothitt", "greek", "japanese",
         "markers", "mathlow", "mathupp", "meteorology", "music", "scriptc", "scripts",
         "symbolic", "timesg", "timesi", "timesib", "timesr", "timesrb"]


class TextTab(BaseTab):
    name = "Text"
    sidebar_tag = "text_sidebar"
    preview_tag = "text_preview"
    log_tag = "text_log"

    def __init__(self):
        super().__init__()
        self.objects = []
        self.selected = -1
        self.document = None
        self.canvas = PreviewCanvas("text_canvas", flip_y=False)
        self.canvases = [self.canvas]

    def build(self, parent):
        with dpg.group(horizontal=True, parent=parent):
            with dpg.child_window(tag=self.sidebar_tag, width=400):
                section("Text Object", pad_top=2)
                dpg.add_input_text(tag="text_content", default_value="Hello", multiline=True,
                                   width=-1, height=70)
                dpg.add_combo(FONTS, label="Font", default_value="futural", tag="text_font",
                              width=160)
                with dpg.group(horizontal=True):
                    dpg.add_text("X")
                    dpg.add_input_text(tag="text_x", default_value="20", width=60)
                    dpg.add_text("Y")
                    dpg.add_input_text(tag="text_y", default_value="40", width=60)
                dpg.add_slider_int(label="Size", tag="text_size", default_value=20,
                                   min_value=5, max_value=100, width=-60)
                dpg.add_input_text(label="Line Spacing", tag="text_spacing",
                                   default_value="0.4", width=80)
                with dpg.group(horizontal=True):
                    dpg.add_checkbox(label="Bold", tag="text_bold")
                    dpg.add_checkbox(label="Italic", tag="text_italic")
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Add", tag="text_btn_add", width=90, callback=self.add)
                    dpg.add_button(label="Update", tag="text_btn_update", width=90,
                                   enabled=False, callback=self.update)
                    dpg.add_button(label="Delete", tag="text_btn_delete", width=-1,
                                   enabled=False, callback=self.delete)

                section("Objects on Canvas")
                dpg.add_listbox([], tag="text_list", num_items=6, callback=self.select)

                section("Output")
                dpg.add_button(label="Preview", width=-1, callback=self.preview)
                dpg.add_button(label="Save SVG", tag="text_btn_save", width=-1,
                               callback=self.save)

                section("Status")
                dpg.add_child_window(tag=self.log_tag, height=130, autosize_x=True)

            with dpg.child_window(tag=self.preview_tag, width=-1, no_scrollbar=True):
                self.canvas.build()

    def apply_button_themes(self):
        dpg.bind_item_theme("text_btn_add", make_button_theme(C_START))
        dpg.bind_item_theme("text_btn_save", make_button_theme(C_START))

    # ------------------------------------------------------------------ #
    def _from_fields(self):
        try:
            return TextObject(
                text=dpg.get_value("text_content"),
                x=float(dpg.get_value("text_x")),
                y=float(dpg.get_value("text_y")),
                font_family=dpg.get_value("text_font"),
                font_size=int(dpg.get_value("text_size")),
                line_spacing=float(dpg.get_value("text_spacing")),
                is_bold=dpg.get_value("text_bold"),
                is_italic=dpg.get_value("text_italic"),
            )
        except ValueError:
            self.log("Invalid numeric field (X, Y, Size or Line Spacing).")
            return None

    def _refresh_list(self):
        dpg.configure_item("text_list", items=[str(o) for o in self.objects])

    def add(self):
        obj = self._from_fields()
        if obj:
            self.objects.append(obj)
            self._refresh_list()

    def select(self, sender, value):
        labels = [str(o) for o in self.objects]
        if value in labels:
            self.selected = labels.index(value)
            o = self.objects[self.selected]
            dpg.set_value("text_content", o.text)
            dpg.set_value("text_x", str(o.x))
            dpg.set_value("text_y", str(o.y))
            dpg.set_value("text_font", o.font_family)
            dpg.set_value("text_size", int(o.font_size))
            dpg.set_value("text_spacing", str(o.line_spacing))
            dpg.set_value("text_bold", o.is_bold)
            dpg.set_value("text_italic", o.is_italic)
            dpg.configure_item("text_btn_update", enabled=True)
            dpg.configure_item("text_btn_delete", enabled=True)

    def update(self):
        if self.selected < 0:
            return
        obj = self._from_fields()
        if obj:
            self.objects[self.selected] = obj
            self._refresh_list()
            self._clear_selection()

    def delete(self):
        if self.selected < 0:
            return
        del self.objects[self.selected]
        self._refresh_list()
        self._clear_selection()

    def _clear_selection(self):
        self.selected = -1
        dpg.configure_item("text_btn_update", enabled=False)
        dpg.configure_item("text_btn_delete", enabled=False)

    # ------------------------------------------------------------------ #
    def _build_command(self):
        cmd = ""
        for obj in self.objects:
            for i, line in enumerate(obj.text.split("\n")):
                y = obj.y + i * obj.font_size * obj.line_spacing
                cmd += f'text -f "{obj.font_family}" -s {obj.font_size} -p {obj.x}mm {y}mm "{line}" '
        return cmd

    def preview(self):
        if not self.objects:
            self.log("No text objects to preview.")
            return
        try:
            self.document = execute(self._build_command())
        except Exception as exc:
            self.log(f"Error generating text SVG: {exc}")
            return
        items, bounds = document_to_items(self.document, is_cmyk=False)
        if bounds is None:
            self.log("Text produced no geometry.")
            return
        self.canvas.set_items(items, bounds)
        self.log("Preview generated.")

    def save(self):
        if self.document is None:
            self.log("Generate a preview first.")
            return
        path = save_file(title="Save SVG")
        if not path:
            self.log("Save cancelled.")
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                vpype.write_svg(f, self.document)
            self.log(f"Saved SVG to {path}.")
            if dpg.does_item_exist("ur10_svg_path"):
                dpg.set_value("ur10_svg_path", path)
                self.log("Loaded into the UR10 tab's SVG file field.")
        except Exception as exc:
            self.log(f"Error saving: {exc}")
