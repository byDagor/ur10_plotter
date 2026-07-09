"""Dither tab: convert an image to a dot field (grayscale or CMYK separation)."""

import os

import dearpygui.dearpygui as dpg
import vpype
from vpype_cli import execute

from vectorizers.dither_vectorizer import run_dither_thread
from dither_converter import _convert_dither_circles_to_points

from .vectorizer_tab import VectorizerTab
from .canvas import document_to_items
from .dialogs import open_file, save_file, IMAGE_TYPES
from .theme import section


class DitherTab(VectorizerTab):
    name = "Dither"
    prefix = "dither"

    def build(self, parent):
        self._wrap(parent, self._controls)
        self._update_param_visibility()

    def _controls(self):
        section("Dither", pad_top=2)
        with dpg.group(horizontal=True):
            dpg.add_input_text(tag="dither_img", width=-88, hint="Source image")
            dpg.add_button(label="Browse", width=80, callback=self._browse)
        dpg.add_input_text(label="Pen Diameter mm", tag="dither_pen",
                           default_value="0.35", width=90)
        dpg.add_slider_int(label="Detail (H dots)", tag="dither_h_dots", default_value=150,
                           min_value=50, max_value=500, width=-120)
        dpg.add_combo(("Floyd-Steinberg", "Ordered (Halftone)", "Stochastic (Random)"),
                      label="Method", default_value="Floyd-Steinberg", tag="dither_method",
                      width=180, callback=self._update_param_visibility)
        dpg.add_slider_float(label="Contrast", tag="dither_contrast", default_value=1.0,
                             min_value=0.1, max_value=3.0, width=-120, format="%.2f")
        dpg.add_slider_float(label="Density", tag="dither_density", default_value=1.0,
                             min_value=0.1, max_value=4.0, width=-120, format="%.2f")
        dpg.add_checkbox(label="Use CMYK Layers", tag="dither_cmyk", callback=self._toggle_cmyk)
        with dpg.group(tag="dither_cmyk_group", show=False):
            with dpg.group(horizontal=True):
                dpg.add_checkbox(label="C", tag="dither_c", default_value=True)
                dpg.add_checkbox(label="M", tag="dither_m", default_value=True)
                dpg.add_checkbox(label="Y", tag="dither_y", default_value=True)
                dpg.add_checkbox(label="K", tag="dither_k", default_value=True)
            dpg.add_input_text(label="Pixel Offset", tag="dither_pixel_offset",
                               default_value="1", width=60)

        self._vectorize_buttons()

        section("Output")
        dpg.add_button(label="Reorder for Shortest Travel", width=-1, callback=self.optimize)
        dpg.add_button(label="Save SVG", tag=f"{self.prefix}_btn_save", width=-1,
                       callback=self.save)

        section("Status")
        dpg.add_child_window(tag=self.log_tag, height=150, autosize_x=True)

    def _toggle_cmyk(self, sender=None, value=None):
        dpg.configure_item("dither_cmyk_group", show=dpg.get_value("dither_cmyk"))
        self._update_param_visibility()

    def _update_param_visibility(self, sender=None, app_data=None):
        # Show only the sliders that actually affect the output for the current
        # method/CMYK selection. Contrast: CMYK or Floyd-Steinberg. Density:
        # grayscale Ordered/Stochastic only. CMYK forces Floyd-Steinberg.
        cmyk = dpg.get_value("dither_cmyk")
        method = dpg.get_value("dither_method")
        dpg.configure_item("dither_contrast", show=(cmyk or method == "Floyd-Steinberg"))
        dpg.configure_item("dither_density", show=(not cmyk and method != "Floyd-Steinberg"))
        dpg.configure_item("dither_method", enabled=not cmyk)

    def _browse(self):
        path = open_file(title="Select image", filetypes=IMAGE_TYPES)
        if path:
            dpg.set_value("dither_img", path)

    def vectorize(self):
        img = dpg.get_value("dither_img")
        if not img or not os.path.exists(img):
            self.log(f"Image not found: {img}")
            return
        try:
            pen = float(dpg.get_value("dither_pen").strip())
            params = {
                "img_path": img,
                "cmyk_dither": dpg.get_value("dither_cmyk"),
                "pen_diameter_mm": pen,
                "dot_radius_mm": pen / 2.0,
                "h_dots": int(dpg.get_value("dither_h_dots")),
            }
        except (ValueError, ZeroDivisionError) as exc:
            self.log(f"Invalid numeric input ({exc}).")
            return

        if params["cmyk_dither"]:
            params["method"] = "Floyd-Steinberg"
            params["contrast_factor"] = dpg.get_value("dither_contrast")
            params["cmyk_channels"] = {
                "c": dpg.get_value("dither_c"), "m": dpg.get_value("dither_m"),
                "y": dpg.get_value("dither_y"), "k": dpg.get_value("dither_k"),
            }
            try:
                params["pixel_offset"] = int(dpg.get_value("dither_pixel_offset"))
            except ValueError:
                params["pixel_offset"] = 0
        else:
            method = dpg.get_value("dither_method")
            params["method"] = method
            params["density"] = dpg.get_value("dither_density")
            params["contrast_factor"] = (dpg.get_value("dither_contrast")
                                         if method == "Floyd-Steinberg" else 1.0)

        self.log("Starting Dither vectorization...")
        self._start(run_dither_thread, (self.bridge, params, self.stop_event))

    def _transform_document(self, doc):
        # Grayscale dither: collapse the transport circles to true center-point
        # dots immediately, so preview/optimize/save/plot are all dots. The
        # worker emits circles only because vpype's SVG reader (used to pass the
        # result back from the dither subprocess) silently drops zero-length
        # points. CMYK stays as circles - it exports per-channel and would lose
        # its layer split otherwise.
        if self.is_cmyk:
            return doc
        return _convert_dither_circles_to_points(doc)

    def render_current(self):
        if not self.document:
            self.canvas.clear()
            return
        # CMYK: filled colour circles. Grayscale: already dots -> "dot" render.
        items, bounds = document_to_items(self.document, self.is_cmyk, fill=self.is_cmyk)
        self.canvas.set_items(items, bounds)

    # ------------------------------------------------------------------ #
    # Reorder (linesort only - merge/simplify do nothing to point dots) + save
    # ------------------------------------------------------------------ #
    def optimize(self):
        if not self.document:
            self.log("Nothing to reorder. Vectorize first.")
            return
        if self.is_cmyk:
            self.log("Reordering CMYK dither is not recommended; save channels individually.")
            return
        self.log("Reordering dots for shortest pen travel...")
        doc = execute("linesort", document=self.document)
        if doc:
            self.document = doc
            self.render_current()
            self.log("Reordered for shortest travel.")
        else:
            self.log("Reorder failed.")

    def save(self):
        if not self.document:
            self.log("Nothing to save. Vectorize first.")
            return
        if self.is_cmyk:
            self._save_cmyk()
            return
        path = save_file(title="Save SVG")
        if not path:
            self.log("Save cancelled.")
            return
        try:
            doc = _convert_dither_circles_to_points(self.document)
            with open(path, "w", encoding="utf-8") as f:
                vpype.write_svg(f, doc)
            self.log(f"Saved SVG to {path}.")
        except Exception as exc:
            self.log(f"Error saving: {exc}")

    def _save_cmyk(self):
        base = save_file(title="Save As (base filename)")
        if not base:
            self.log("Save cancelled.")
            return
        base_dir = os.path.dirname(base)
        base_name = os.path.splitext(os.path.basename(base))[0]
        channel_map = {1: "_C", 2: "_M", 3: "_Y", 4: "_K"}
        try:
            full = self.document.bounds()
            if not full:
                self.log("Cannot save: document has no bounds.")
                return
            min_x, min_y, max_x, max_y = full
            corner_lines = vpype.LineCollection([
                vpype.line(min_x, min_y, min_x, min_y),
                vpype.line(max_x, max_y, max_x, max_y),
            ])
            saved = []
            for layer_id, suffix in channel_map.items():
                if layer_id in self.document.layers:
                    layer_doc = vpype.Document()
                    layer_doc.add(vpype.LineCollection(self.document.layers[layer_id]))
                    layer_doc.add(corner_lines)
                    layer_doc = _convert_dither_circles_to_points(layer_doc)
                    fname = os.path.join(base_dir, f"{base_name}{suffix}.svg")
                    with open(fname, "w", encoding="utf-8") as f:
                        vpype.write_svg(f, layer_doc)
                    saved.append(fname)
            self.log(f"Saved {len(saved)} CMYK channel files: " + ", ".join(os.path.basename(s) for s in saved))
        except Exception as exc:
            self.log(f"Error saving CMYK files: {exc}")
