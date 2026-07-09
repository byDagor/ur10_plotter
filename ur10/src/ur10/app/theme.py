"""Shared palette, theming, and small layout helpers."""

import dearpygui.dearpygui as dpg

# --------------------------------------------------------------------------- #
# Palette
# --------------------------------------------------------------------------- #
BG          = (26, 28, 32)
PANEL       = (34, 37, 43)
CANVAS_BG   = (250, 250, 250)
ACCENT      = (64, 132, 214)
TEXT_DIM    = (150, 156, 166)
INK         = (20, 20, 24)
PAPER_EDGE  = (205, 208, 214)

C_CONNECT = (56, 120, 200)
C_START   = (46, 160, 84)
C_PAUSE   = (214, 146, 40)
C_STOP    = (200, 62, 62)
C_NEUTRAL = (72, 78, 90)

# CMYK layer colours (vpype layers 1..4) for previews on white paper.
CMYK = {1: (0, 160, 200), 2: (210, 40, 160), 3: (200, 170, 0), 4: INK}

# Shared sizing
SIDEBAR_W = 400
MARGIN_W  = 58
TABBAR_H  = 42


def shift(rgb, d):
    return tuple(max(0, min(255, c + d)) for c in rgb)


def make_button_theme(rgb):
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, rgb)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, shift(rgb, 18))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, shift(rgb, -18))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (245, 246, 248))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 5)
    return theme


def build_global_theme():
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, BG)
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, shift(PANEL, 10))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, shift(PANEL, 22))
            dpg.add_theme_color(dpg.mvThemeCol_Button, C_NEUTRAL)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, shift(C_NEUTRAL, 18))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, shift(C_NEUTRAL, -14))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, shift(ACCENT, 20))
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark, ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_Tab, PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_TabActive, shift(ACCENT, -40))
            dpg.add_theme_color(dpg.mvThemeCol_TabHovered, shift(ACCENT, -20))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 5)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 8)
            dpg.add_theme_style(dpg.mvStyleVar_TabRounding, 6)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 7, 5)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 7)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 12, 10)
    return theme


def section(label, pad_top=6):
    dpg.add_spacer(height=pad_top)
    dpg.add_text(label.upper(), color=ACCENT)
    dpg.add_separator()
    dpg.add_spacer(height=1)
