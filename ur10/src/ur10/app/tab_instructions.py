"""Instructions tab: parameter reference for each mode."""

import dearpygui.dearpygui as dpg

from robot.ur10_controller import SAFE_Z_OFFSET, PEN_CHANGE_Z_OFFSET

from .tabbase import BaseTab
from .theme import ACCENT, TEXT_DIM

SAFE_MM = SAFE_Z_OFFSET * 1000
PEN_MM = PEN_CHANGE_Z_OFFSET * 1000

SECTIONS = {
    "Flow Imager": [
        ("Noise Coeff", "Controls 'wiggliness'. 0.0 is smooth, 0.05 is chaotic."),
        ("Min/Max Separation", "Controls line density, in mm."),
        ("Min/Max Length", "Filters lines that are too short or too long, in mm."),
        ("Max Size", "Downscales the image to this dimension in px. 1600 is a good default."),
        ("N Fields", "Overlays multiple flow fields for cross-hatching."),
        ("Edge Flow", "How strongly lines follow hard edges / outlines."),
        ("Dark Flow", "How strongly lines swirl around dark areas."),
        ("Rotate", "Rotates the flow field before drawing, in degrees."),
        ("CMYK", "Separates into C, M, Y, K layers (1-4) for multi-pen plotting."),
        ("K-d Tree", "Alternate search algorithm; uncheck if you hit errors."),
        ("Trim Border", "Removes lines that sit exactly on the image border."),
    ],
    "Hatched": [
        ("Image Scale", "Downscales the image (0.5 = 50%) for performance."),
        ("Hatch Offset", "Shifts the starting point of the hatch pattern, in px."),
        ("Gaussian Blur", "Blurs the image before finding contours. 0 sharp, 5 soft."),
        ("Hatch Pitch", "Base line spacing in the darkest areas. Smaller = denser."),
        ("Hatch Angles", "Line directions in degrees. '45 135' cross-hatches."),
        ("Levels", "Grayscale thresholds for shading, e.g. 64 128 192."),
        ("Interpolation", "INTER_LINEAR is smooth; INTER_NEAREST is pixelated."),
        ("Circular Center", "Center for circular hatches; 0.5 0.5 is the middle."),
        ("Invert / Circular / H-Mirror", "Invert shading, use concentric circles, or flip horizontally."),
        ("Draw Contours / Hatch Fill", "Draw shape outlines and/or the shading lines."),
    ],
    "Dither": [
        ("Pen Diameter", "Diameter of the pen used for the dots, in mm."),
        ("Detail (H dots)", "Number of horizontal dot positions; sets output resolution."),
        ("Method", "Floyd-Steinberg (organic), Ordered (grid), or Stochastic (random)."),
        ("Contrast", "Used by Floyd-Steinberg / CMYK. Adjusts contrast before dithering."),
        ("Density", "Used by Ordered / Stochastic. Adjusts overall darkness."),
        ("CMYK Layers", "Separate into C/M/Y/K channels; save each as its own file."),
        ("Pixel Offset", "Per-channel dot offset (CMYK) to reduce overlap."),
        ("Reorder for Shortest Travel", "Dots are generated in raster order, which makes the pen "
         "jump back across the page at the end of every row. This reorders them to minimize "
         "pen-up travel (typically ~60% less). Save afterward, then plot that file from the UR10 tab."),
    ],
    "Text": [
        ("Content", "Text to plot; line breaks are supported."),
        ("Font", "A single-stroke (Hershey) font."),
        ("Pos X / Y", "Position of the text in mm."),
        ("Size", "Font size in mm."),
        ("Line Spacing", "Spacing between lines as a multiple of the font size."),
        ("Add / Update / Delete", "Manage the list of text objects on the canvas."),
        ("Preview / Save SVG", "Render the combined text, then export it (and load it into UR10)."),
    ],
    "UR10 Control": [
        ("Robot IP", "IP address of the UR10 robot."),
        ("Connect", "Connect to the robot; the Run controls enable once connected."),
        ("SVG File", "The SVG to plot; dithered files auto-render as dots."),
        ("Set Home", "Move so the pen touches the canvas corner, then set the drawing Z-height. "
                     f"Travel moves happen {SAFE_MM:.0f} mm above this point."),
        ("Corner / Rotation", "Origin corner and drawing rotation about the home point."),
        ("Canvas Width/Height", "Target canvas size in mm; the SVG is scaled to fit."),
        ("Speed / Accel", "Motion parameters in m/s and m/s^2."),
        ("Dry Run", f"Robot stays at the safe travel height ({SAFE_MM:.0f} mm up); the pen never touches."),
        ("Start / Pause / Stop", "Begin, pause (lifts pen, returns home), or stop plotting."),
        ("Go Home", f"Move to the safe home position ({SAFE_MM:.0f} mm above the canvas)."),
        ("Pen Change", f"Move to a pen-swap position ({PEN_MM:.0f} mm above the canvas)."),
        ("Check Canvas", "Trace the canvas perimeter at the safe height to verify placement."),
        ("Demo Draw", "Preview the drawing upright, animated, without moving the robot."),
    ],
}


class InstructionsTab(BaseTab):
    name = "Instructions"
    preview_tag = "instr_scroll"

    def __init__(self):
        super().__init__()
        self.canvases = []

    def build(self, parent):
        with dpg.child_window(tag=self.preview_tag, parent=parent):
            with dpg.tab_bar():
                for title, rows in SECTIONS.items():
                    with dpg.tab(label=title):
                        dpg.add_spacer(height=6)
                        for label, desc in rows:
                            dpg.add_text(label, color=ACCENT)
                            dpg.add_text(desc, wrap=760, indent=16, color=TEXT_DIM)
                            dpg.add_spacer(height=4)

    def relayout(self, content_w, content_h):
        if dpg.does_item_exist(self.preview_tag):
            dpg.configure_item(self.preview_tag, height=content_h, width=content_w)
