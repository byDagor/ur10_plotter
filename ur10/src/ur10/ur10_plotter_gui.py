import FreeSimpleGUI as sg
import vpype
from vpype_cli import execute

import os
import threading
from typing import Union
import cv2
import json
import math

from gui_layout import create_layout
from gui_preview import update_preview, update_svg_preview, update_flow_preview, update_hatched_preview, update_dither_preview, update_text_preview, preview_dots_from_svg
from vectorizers.flow_vectorizer import run_vectorize_thread
from vectorizers.hatched_vectorizer import run_hatched_thread
from vectorizers.dither_vectorizer import run_dither_thread
from robot.ur10_controller import UR10Controller, SAFE_Z_OFFSET, RobotStatus
from robot.svg_parser import parse_svg
from dither_converter import _convert_dither_circles_to_points
from text_object import TextObject


def main():
    """
    Main event loop for the application.
    """
    
    layout = create_layout()
    window = sg.Window("PLOTTUR10", layout, finalize=True, resizable=True)
    
    stop_flow_event = threading.Event()
    stop_hatched_event = threading.Event()
    stop_dither_event = threading.Event()
    
    text_objects = []
    selected_index = -1
    
    # Load home position from config file
    home_pose = None
    try:
        with open("home_config.json", "r") as f:
            config = json.load(f)
            home_pose = config.get("pose")
            corner = config.get("corner", "Top Left")
            if home_pose:
                pose_str = ", ".join([f"{x:.3f}" for x in home_pose])
                window["-HOME_POSE_DISPLAY-"].update(pose_str)
                window["-CANVAS_CORNER-"].update(corner)
                print(f"Loaded home position: {pose_str}")
    except FileNotFoundError:
        print("home_config.json not found. Please set a home position.")
    except (json.JSONDecodeError, KeyError):
        print("Error reading home_config.json. File might be corrupted.")

    flow_document: Union[vpype.Document, None] = None
    hatched_document: Union[vpype.Document, None] = None
    dither_document: Union[vpype.Document, None] = None
    text_document: Union[vpype.Document, None] = None
    dither_is_cmyk = False

    ur10_controller: Union[UR10Controller, None] = None
    scaled_dims = {"width": 0, "height": 0}
    
    # Clear all previews at startup
    update_flow_preview(window, None, is_cmyk=False)
    update_hatched_preview(window, None, is_cmyk=False)
    update_dither_preview(window, None)
    update_svg_preview(window, None)

    # --- SVG Text Logic ---
    def get_settings_from_gui(values):
        try:
            return TextObject(
                text=values["-TEXT_INPUT-"],
                x=float(values["-TEXT_POS_X-"]),
                y=float(values["-TEXT_POS_Y-"]),
                font_family=values["-TEXT_FONT-"],
                font_size=int(values["-TEXT_FONT_SIZE-"]),
                line_spacing=float(values["-TEXT_LINE_SPACING-"]),
                is_bold=values["-TEXT_BOLD-"],
                is_italic=values["-TEXT_ITALIC-"]
            )
        except ValueError:
            return None

    # --- Event Loop ---
    try:
        while True:
            event, values = window.read()

            if event == sg.WIN_CLOSED:
                break
            
            if event == "-LOG_MESSAGE-":
                active_tab = values["-TABGROUP-"]
                if active_tab == "-TAB_FLOW-":
                    window["-LOG_FLOW-"].print(values[event])
                elif active_tab == "-TAB_HATCHED-":
                    window["-LOG_HATCHED-"].print(values[event])
                elif active_tab == "-TAB_DITHER-":
                    window["-LOG_DITHER-"].print(values[event])
                elif active_tab == "-TAB_TEXT-":
                    window["-LOG_TEXT-"].print(values[event])
                else:
                    print(f"Log message from unhandled tab '{active_tab}': {values[event]}")
                continue
            
            try:
                # --- Vectorize Image Event ---
                if event == "-BTN_VECTORIZE_FLOW-":
                    print("Vectorizing image with Flow Imager...")
                    img_path = values["-IMG_PATH_FLOW-"]
                    noise_str = values["-FLOW_NOISE-"].strip()
                    min_sep = values["-FLOW_MIN_SEP-"]
                    max_sep = values["-FLOW_MAX_SEP-"]
                    cmyk = values["-FLOW_CMYK-"]
                    n_fields = int(values["-FLOW_N_FIELDS-"])
                    min_len_str = values["-FLOW_MIN_LEN-"].strip().replace("mm", "").strip()
                    max_len_str = values["-FLOW_MAX_LEN-"].strip().replace("mm", "").strip()
                    max_size_str = values["-FLOW_MAX_SIZE-"].strip().replace("px", "").strip()
                    edge_flow = values["-FLOW_EDGE-"]
                    dark_flow = values["-FLOW_DARK-"]
                    rotate = int(values["-FLOW_ROTATE-"])
                    kdt = values["-FLOW_KDT-"]
                    trim = values["-FLOW_TRIM-"]
                    if not img_path or not os.path.exists(img_path):
                        print(f"Error: Image file not found or not specified: {img_path}")
                        continue
                    try:
                        noise = float(noise_str)
                        cmd_string = f"flow_img -nc {noise} -ms {min_sep}mm -Ms {max_sep}mm"
                    except ValueError:
                        print(f"Invalid Noise Coeff: {noise_str}. Must be a number.")
                        continue
                    if n_fields != 1: cmd_string += f" -nf {n_fields}"
                    try:
                        min_len = float(min_len_str)
                        if min_len > 0: cmd_string += f" -ml {min_len}mm"
                    except ValueError: print(f"Ignoring invalid Min Length: {min_len_str}")
                    try:
                        max_len = float(max_len_str)
                        if max_len > 0: cmd_string += f" -Ml {max_len}mm"
                    except ValueError: print(f"Ignoring invalid Max Length: {max_len_str}")
                    try:
                        max_size = int(max_size_str)
                        if max_size > 0: cmd_string += f" --max_size {max_size}"
                    except ValueError: print(f"Ignoring invalid Max Size: {max_size_str}")
                    if edge_flow != 1.0: cmd_string += f" -efm {edge_flow}"
                    if dark_flow != 1.0: cmd_string += f" -dfm {dark_flow}"
                    if rotate != 0: cmd_string += f" --rotate {rotate}"
                    if cmyk: cmd_string += " --cmyk"
                    if kdt: cmd_string += " -kdt"
                    if trim: cmd_string += " -tm"
                    cmd_string += f" \"{img_path}\""
                    window["-LOG_FLOW-"].print("Starting Flow Imager vectorization... please wait.")
                    stop_flow_event.clear()
                    window["-BTN_VECTORIZE_FLOW-"].update(disabled=True)
                    window["-BTN_STOP_FLOW-"].update(disabled=False)
                    threading.Thread(target=run_vectorize_thread, args=(window, cmd_string, cmyk, stop_flow_event), daemon=True).start()

                elif event == "-BTN_VECTORIZE_HATCHED-":
                    print("Vectorizing image with Hatched...")
                    img_path = values["-IMG_PATH_HATCHED-"]
                    if not img_path or not os.path.exists(img_path):
                        print(f"Error: Image file not found or not specified: {img_path}")
                        continue
                    params = {}
                    params["img_path"] = img_path
                    params["cmyk"] = values["-HATCHED_CMYK-"]
                    params["invert"] = values["-HATCHED_INVERT-"]
                    params["lines"] = values["-HATCHED_LINES-"]
                    params["hatch"] = values["-HATCHED_HATCH-"]
                    params["pitch"] = values["-HATCHED_PITCH-"]
                    params["blur"] = values["-HATCHED_BLUR-"]
                    params["circular"] = values["-HATCHED_CIRCULAR-"]
                    params["image_scale"] = values["-HATCHED_SCALE-"]
                    params["h_mirror"] = values["-HATCHED_HMIRROR-"]
                    params["interpolation"] = cv2.INTER_LINEAR if values["-HATCHED_INTERP-"] == "INTER_LINEAR" else cv2.INTER_NEAREST
                    try: params["offset"] = float(values["-HATCHED_OFFSET-"].strip())
                    except ValueError:
                        print(f"Invalid Offset: {values['-HATCHED_OFFSET-']}. Using 0.0.")
                        params["offset"] = 0.0
                    try:
                        center_coords = [float(c) for c in values["-HATCHED_CENTER-"].strip().split()]
                        if len(center_coords) == 2: params["center"] = (center_coords[0], center_coords[1])
                        else: raise ValueError("Center must be two numbers")
                    except ValueError:
                        print(f"Invalid Center: {values['-HATCHED_CENTER-']}. Using (0.5, 0.5).")
                        params["center"] = (0.5, 0.5)
                    try:
                        angles = [float(a) for a in values["-HATCHED_ANGLES-"].strip().split()]
                        if not angles: angles = [45.0]
                        params["angle"] = angles
                    except ValueError:
                        print(f"Invalid Hatch Angles: {values['-HATCHED_ANGLES-']}. Using 45.")
                        params["angle"] = [45.0]
                    try:
                        levels = [int(level_str) for level_str in values["-HATCHED_LEVELS-"].strip().split() if 0 < int(level_str) < 255]
                        if not levels: levels = (64, 128, 192)
                        params["levels"] = tuple(levels)
                    except ValueError:
                        print(f"Invalid Levels: {values['-HATCHED_LEVELS-']}. Using defaults.")
                        params["levels"] = (64, 128, 192)
                    window["-LOG_HATCHED-"].print("Starting Hatched vectorization... please wait.")
                    stop_hatched_event.clear()
                    window["-BTN_VECTORIZE_HATCHED-"].update(disabled=True)
                    window["-BTN_STOP_HATCHED-"].update(disabled=False)
                    threading.Thread(target=run_hatched_thread, args=(window, params, stop_hatched_event), daemon=True).start()

                elif event == "-BTN_VECTORIZE_DITHER-":
                    print("Vectorizing image with Dither...")
                    img_path = values["-IMG_PATH_DITHER-"]
                    if not img_path or not os.path.exists(img_path):
                        print(f"Error: Image file not found or not specified: {img_path}")
                        continue
                    
                    params = {"img_path": img_path}
                    params["cmyk_dither"] = values["-DITHER_CMYK-"]
                    
                    try:
                        params["pen_diameter_mm"] = float(values["-DITHER_PEN_DIAMETER-"].strip())
                        params["h_dots"] = int(values["-DITHER_H_DOTS-"])
                        params["dot_radius_mm"] = params["pen_diameter_mm"] / 2.0

                        if params["cmyk_dither"]:
                            params["method"] = "Floyd-Steinberg" 
                            params["contrast_factor"] = values["-DITHER_CONTRAST-"]
                            params["cmyk_channels"] = {
                                'c': values["-DITHER_CMYK_C-"],
                                'm': values["-DITHER_CMYK_M-"],
                                'y': values["-DITHER_CMYK_Y-"],
                                'k': values["-DITHER_CMYK_K-"]
                            }
                            params["pixel_offset"] = int(values["-DITHER_PIXEL_OFFSET-"])
                        else:
                            params["method"] = values["-DITHER_METHOD-"]
                            params["density"] = values["-DITHER_DENSITY-"]
                            if values["-DITHER_METHOD-"] == "Floyd-Steinberg":
                                params["contrast_factor"] = values["-DITHER_CONTRAST-"]
                            else:
                                params["contrast_factor"] = 1.0

                    except (ValueError, ZeroDivisionError) as e:
                        print(f"Error: Invalid numeric input. Please check your values. ({e})")
                        continue

                    window["-LOG_DITHER-"].print("Starting Dither vectorization... please wait.")
                    stop_dither_event.clear()
                    window["-BTN_VECTORIZE_DITHER-"].update(disabled=True)
                    window["-BTN_STOP_DITHER-"].update(disabled=False)
                    threading.Thread(target=run_dither_thread, args=(window, params, stop_dither_event), daemon=True).start()

                elif event == "-TEXT_ADD-":
                    new_obj = get_settings_from_gui(values)
                    if new_obj:
                        text_objects.append(new_obj)
                        window["-TEXT_LIST-"].update([str(o) for o in text_objects])

                elif event == "-TEXT_LIST-" and len(values["-TEXT_LIST-"]) > 0:
                    indexes = window["-TEXT_LIST-"].get_indexes()
                    if indexes:
                        selected_index = indexes[0]
                        obj = text_objects[selected_index]
                        
                        window["-TEXT_INPUT-"].update(obj.text)
                        window["-TEXT_POS_X-"].update(obj.x)
                        window["-TEXT_POS_Y-"].update(obj.y)
                        window["-TEXT_FONT-"].update(obj.font_family)
                        window["-TEXT_FONT_SIZE-"].update(obj.font_size)
                        window["-TEXT_LINE_SPACING-"].update(obj.line_spacing)
                        window["-TEXT_BOLD-"].update(obj.is_bold)
                        window["-TEXT_ITALIC-"].update(obj.is_italic)
                        
                        window["-TEXT_UPDATE-"].update(disabled=False)
                        window["-TEXT_DELETE-"].update(disabled=False)

                elif event == "-TEXT_UPDATE-" and selected_index >= 0:
                    updated_obj = get_settings_from_gui(values)
                    if updated_obj:
                        text_objects[selected_index] = updated_obj
                        window["-TEXT_LIST-"].update([str(o) for o in text_objects])
                        window["-TEXT_UPDATE-"].update(disabled=True)
                        window["-TEXT_DELETE-"].update(disabled=True)
                        selected_index = -1
                
                elif event == "-TEXT_DELETE-" and selected_index >= 0:
                    del text_objects[selected_index]
                    window["-TEXT_LIST-"].update([str(o) for o in text_objects])
                    window["-TEXT_UPDATE-"].update(disabled=True)
                    window["-TEXT_DELETE-"].update(disabled=True)
                    selected_index = -1

                elif event == "-TEXT_PREVIEW-":
                    if not text_objects:
                        window["-LOG_TEXT-"].print("No text objects to preview.")
                        continue
                    
                    cmd_str = ""
                    for obj in text_objects:
                        lines = obj.text.split('\n')
                        for i, line in enumerate(lines):
                            y_pos = obj.y + i * obj.font_size * obj.line_spacing
                            cmd_str += f"text -f \"{obj.font_family}\" -s {obj.font_size} -p {obj.x}mm {y_pos}mm \"{line}\" "

                    try:
                        window["-LOG_TEXT-"].print("Generating SVG preview from text objects...")
                        doc = execute(cmd_str)
                        text_document = doc
                        update_text_preview(window, text_document)
                        window["-LOG_TEXT-"].print("Preview generated successfully.")
                        window["-TEXT_SAVE_SVG-"].update(disabled=False)
                    except Exception as e:
                        window["-LOG_TEXT-"].print(f"Error generating SVG: {e}")
                        sg.popup_error(f"Error generating SVG: {e}")

                elif event == "-TEXT_SAVE_SVG-":
                    if text_document is None:
                        window["-LOG_TEXT-"].print("No SVG document to save. Generate one first.")
                        continue
                    
                    try:
                        save_path = sg.popup_get_file("Save As", save_as=True, no_window=True, default_extension=".svg", file_types=(("SVG", "*.svg"),))
                        if save_path:
                            window["-LOG_TEXT-"].print(f"Saving SVG to {save_path}...")
                            with open(save_path, "w", encoding="utf-8") as f:
                                vpype.write_svg(f, text_document)
                            window["-LOG_TEXT-"].print("SVG file saved successfully.")
                            window["-SVG_PATH-"].update(save_path)
                            window["-TAB_UR10-"].select()
                    except Exception as e:
                        window["-LOG_TEXT-"].print(f"Error saving file: {e}")
                        sg.popup_error(f"Error saving file: {e}")

                elif event == "-DITHER_CMYK-":
                    is_cmyk = values[event]
                    window['-COL_DITHER_CMYK-'].update(visible=is_cmyk)
                    window['-DITHER_METHOD-'].update(disabled=is_cmyk)
                    window['-COL_DENSITY-'].update(visible=not is_cmyk and values['-DITHER_METHOD-'] != "Floyd-Steinberg")
                    # Contrast is used for both, so keep it visible but maybe change label?
                    window['-COL_CONTRAST-'].update(visible=is_cmyk or values['-DITHER_METHOD-'] == "Floyd-Steinberg")


                elif event == "-DITHER_METHOD-":
                    if values[event] == "Floyd-Steinberg":
                        window['-COL_CONTRAST-'].update(visible=True)
                        window['-COL_DENSITY-'].update(visible=False)
                    else:
                        window['-COL_CONTRAST-'].update(visible=False)
                        window['-COL_DENSITY-'].update(visible=True)
                
                # --- Event for when the thread is done ---
                elif event == "-THREAD_DONE-":
                    doc_from_thread, message, is_cmyk = values[event]
                    
                    if isinstance(message, RobotStatus):
                        window["-UR10_STATUS-"].print(message.value)
                        window["-BTN_START-"].update(disabled=False)
                        window["-BTN_PAUSE-"].update(text="Pause", disabled=True)
                        window["-BTN_STOP-"].update(disabled=True)
                        window["-BTN_UR10_HOME-"].update(disabled=False)
                        window["-BTN_CHECK_CANVAS-"].update(disabled=False)
                        window["-BTN_PEN_CHANGE-"].update(disabled=False)
                        if message == RobotStatus.EXECUTION_COMPLETE:
                            if ur10_controller and home_pose:
                                window["-UR10_STATUS-"].print("Moving to pen change position...")
                                ur10_controller.go_to_pen_change_position(home_pose)
                                window["-UR10_STATUS-"].print("Robot is at pen change position.")
                        continue

                    if ("Flow Imager" in message and stop_flow_event.is_set()) or \
                       ("Hatched" in message and stop_hatched_event.is_set()) or \
                       ("Dither" in message and stop_dither_event.is_set()):
                        continue

                    if "Flow Imager" in message:
                        window["-BTN_VECTORIZE_FLOW-"].update(disabled=False)
                        window["-BTN_STOP_FLOW-"].update(disabled=True)
                    elif "Hatched" in message:
                        window["-BTN_VECTORIZE_HATCHED-"].update(disabled=False)
                        window["-BTN_STOP_HATCHED-"].update(disabled=True)
                    elif "Dither" in message:
                        window["-BTN_VECTORIZE_DITHER-"].update(disabled=False)
                        window["-BTN_STOP_DITHER-"].update(disabled=True)
                    
                    if "vectorization complete." not in message:
                        print(f"Thread Error: {message}")
                        sg.popup_error(f"Vectorization Failed:\n\n{message}")
                    elif doc_from_thread:
                        log_key = "-LOG_FLOW-"
                        if "Hatched" in message: log_key = "-LOG_HATCHED-"
                        elif "Dither" in message: log_key = "-LOG_DITHER-"
                        window[log_key].print(message)
                        
                        if "Flow Imager" in message:
                            flow_document = doc_from_thread
                            update_flow_preview(window, flow_document, is_cmyk)
                        elif "Hatched" in message:
                            hatched_document = doc_from_thread
                            update_hatched_preview(window, hatched_document, is_cmyk)
                        elif "Dither" in message:
                            dither_document = doc_from_thread
                            dither_is_cmyk = is_cmyk
                            update_dither_preview(window, dither_document, is_cmyk)
                    else:
                        log_key = "-LOG_FLOW-"
                        if "Hatched" in message: log_key = "-LOG_HATCHED-"
                        elif "Dither" in message: log_key = "-LOG_DITHER-"
                        window[log_key].print("Thread finished but document is empty.")

                        if "Flow Imager" in message: flow_document = None
                        elif "Hatched" in message: hatched_document = None
                        elif "Dither" in message:
                            dither_document = None
                            dither_is_cmyk = False
                        
                        update_flow_preview(window, None, is_cmyk=False)
                        update_hatched_preview(window, None, is_cmyk=False)
                        update_dither_preview(window, None, is_cmyk=False)
                
                # --- Vectorizer Stop Events ---
                elif event == "-BTN_STOP_FLOW-":
                    stop_flow_event.set()
                    window["-BTN_VECTORIZE_FLOW-"].update(disabled=False)
                    window["-BTN_STOP_FLOW-"].update(disabled=True)
                    window["-LOG_FLOW-"].print("Flow Imager vectorization stopped by user.")

                elif event == "-BTN_STOP_HATCHED-":
                    stop_hatched_event.set()
                    window["-BTN_VECTORIZE_HATCHED-"].update(disabled=False)
                    window["-BTN_STOP_HATCHED-"].update(disabled=True)
                    window["-LOG_HATCHED-"].print("Hatched vectorization stopped by user.")

                elif event == "-BTN_STOP_DITHER-":
                    stop_dither_event.set()
                    window["-BTN_VECTORIZE_DITHER-"].update(disabled=False)
                    window["-BTN_STOP_DITHER-"].update(disabled=True)
                    window["-LOG_DITHER-"].print("Dither vectorization stopped by user.")

                # --- SVG Preview Event ---
                elif event == "-SVG_PATH-":
                    file_path = values["-SVG_PATH-"]
                    if file_path and os.path.exists(file_path):
                        render_as_dots = values["-RENDER_AS_DOTS-"]
                        
                        if render_as_dots:
                            preview_dots_from_svg(window, file_path)
                        else:
                            try:
                                doc = execute(f'read "{file_path}"')
                                update_svg_preview(window, doc)
                            except Exception as e:
                                window["-UR10_STATUS-"].print(f"Error loading SVG with vpype: {e}")
                                update_svg_preview(window, None)
                        window["-TAB_SVG_PREVIEW-"].select() 
                    else:
                        update_svg_preview(window, None)
                
                # --- Optimize Event ---
                elif event in ("-BTN_OPTIMIZE-", "-BTN_OPTIMIZE-HATCHED-", "-BTN_OPTIMIZE-DITHER-"):
                    
                    is_flow = event == "-BTN_OPTIMIZE-"
                    is_hatched = event == "-BTN_OPTIMIZE-HATCHED-"
                    is_dither = event == "-BTN_OPTIMIZE-DITHER-"

                    doc_to_optimize = None
                    if is_flow: doc_to_optimize = flow_document
                    elif is_hatched: doc_to_optimize = hatched_document
                    elif is_dither:
                        doc_to_optimize = dither_document
                        if doc_to_optimize and not dither_is_cmyk:
                            window["-LOG_DITHER-"].print("Converting dither circles to points for optimization...")
                            doc_to_optimize = _convert_dither_circles_to_points(doc_to_optimize)
                        elif dither_is_cmyk:
                             window["-LOG_DITHER-"].print("Optimization of CMYK dither is not recommended. Save files individually.")
                             continue


                    log_key = "-LOG_FLOW-"
                    if is_hatched: log_key = "-LOG_HATCHED-"
                    elif is_dither: log_key = "-LOG_DITHER-"
                    
                    if doc_to_optimize is None:
                        window[log_key].print("No drawing to optimize. Generate one first.")
                        continue
                    
                    window[log_key].print("Optimizing drawing... please wait.")
                    
                    merge_tol, simplify_tol = "0.1", "0.05"
                    if is_flow:
                        merge_tol = values["-OPT_MERGE-"].strip().replace("mm", "").strip()
                        simplify_tol = values["-OPT_SIMPLIFY-"].strip().replace("mm", "").strip()
                    elif is_hatched:
                        merge_tol = values["-OPT_MERGE-HATCHED-"].strip().replace("mm", "").strip()
                        simplify_tol = values["-OPT_SIMPLIFY-HATCHED-"].strip().replace("mm", "").strip()
                    elif is_dither:
                        merge_tol = values["-OPT_MERGE-DITHER-"].strip().replace("mm", "").strip()
                        simplify_tol = values["-OPT_SIMPLIFY-DITHER-"].strip().replace("mm", "").strip()
                    
                    cmd_string = f"linemerge -t {merge_tol}mm linesimplify -t {simplify_tol}mm linesort"
                    
                    print(f"Running command: vpype {cmd_string}")
                    optimized_doc = execute(cmd_string, document=doc_to_optimize)
                    
                    if optimized_doc:
                        window[log_key].print("Optimization complete. Updating preview.")
                        is_cmyk_preview = False
                        
                        if is_flow:
                            flow_document = optimized_doc
                            is_cmyk_preview = values["-FLOW_CMYK-"]
                            update_preview(window, optimized_doc, is_cmyk_preview, image_key="-PREVIEW_IMAGE_FLOW-")
                        elif is_hatched:
                            hatched_document = optimized_doc
                            is_cmyk_preview = values["-HATCHED_CMYK-"]
                            update_preview(window, optimized_doc, is_cmyk_preview, image_key="-PREVIEW_IMAGE_HATCHED-")
                        elif is_dither:
                            dither_document = optimized_doc
                            # After optimization, it's no longer CMYK in the same way
                            dither_is_cmyk = False 
                            update_preview(window, optimized_doc, False, image_key="-PREVIEW_IMAGE_DITHER-")
                    else:
                        window[log_key].print("Optimization failed.")

                # --- Save Event ---
                elif event in ("-BTN_SAVE-", "-BTN_SAVE-HATCHED-", "-BTN_SAVE-DITHER-"):
                    
                    doc_to_save, log_key = None, "-LOG_FLOW-"
                    if event == "-BTN_SAVE-": doc_to_save = flow_document
                    elif event == "-BTN_SAVE-HATCHED-":
                        doc_to_save = hatched_document
                        log_key = "-LOG_HATCHED-"
                    elif event == "-BTN_SAVE-DITHER-":
                        doc_to_save = dither_document
                        log_key = "-LOG_DITHER-"

                    if doc_to_save is None:
                        window[log_key].print("Error: No document to save. Generate or optimize first.")
                        continue
                    
                    # Special handling for CMYK Dither save
                    if event == "-BTN_SAVE-DITHER-" and dither_is_cmyk:
                        save_path = sg.popup_get_file("Save As (Base Filename)", save_as=True, no_window=True, default_extension=".svg", file_types=(("SVG", "*.svg"),))
                        if not save_path:
                            window[log_key].print("SVG save cancelled.")
                            continue

                        base_dir = os.path.dirname(save_path)
                        base_name = os.path.splitext(os.path.basename(save_path))[0]
                        channel_map = {1: '_C', 2: '_M', 3: '_Y', 4: '_K'}
                        files_saved = []

                        try:
                            full_bounds = doc_to_save.bounds()
                            if not full_bounds:
                                sg.popup_error("Cannot save, document has no bounds.")
                                continue

                            min_x, min_y, max_x, max_y = full_bounds
                            corner_lines = vpype.LineCollection([
                                vpype.line(min_x, min_y, min_x, min_y),
                                vpype.line(max_x, max_y, max_x, max_y)
                            ])

                            for layer_id, suffix in channel_map.items():
                                if layer_id in doc_to_save.layers:
                                    layer_doc = vpype.Document()
                                    # Add the actual geometry for the layer
                                    layer_doc.add(vpype.LineCollection(doc_to_save.layers[layer_id]))
                                    # Add the corner points to enforce the bounding box
                                    layer_doc.add(corner_lines)
                                    
                                    window[log_key].print(f"Converting layer {suffix} circles to points...")
                                    layer_doc_points = _convert_dither_circles_to_points(layer_doc)

                                    file_name = os.path.join(base_dir, f"{base_name}{suffix}.svg")
                                    window[log_key].print(f"Saving {file_name}...")
                                    with open(file_name, "w", encoding="utf-8") as f:
                                        vpype.write_svg(f, layer_doc_points)
                                    files_saved.append(file_name)
                            
                            sg.popup("CMYK Dither Save Complete", f"Saved {len(files_saved)} files:\n" + "\n".join(files_saved))

                        except Exception as e:
                            print(f"Error saving CMYK dither files: {e}")
                            sg.popup_error(f"Error saving CMYK dither files: {e}")
                        continue


                    # Standard save for all other cases
                    if event == "-BTN_SAVE-DITHER-" and doc_to_save:
                        window[log_key].print("Converting dither circles to points for saving...")
                        doc_to_save = _convert_dither_circles_to_points(doc_to_save)

                    save_path = sg.popup_get_file("Save As", save_as=True, no_window=True, default_extension=".svg", file_types=(("SVG", "*.svg"),))

                    if save_path:
                        try:
                            window[log_key].print(f"Saving SVG to {save_path}...")
                            with open(save_path, "w", encoding="utf-8") as f:
                                vpype.write_svg(f, doc_to_save)
                            window[log_key].print("SVG file saved successfully.")
                        except Exception as e:
                            print(f"Error saving file: {e}")
                            sg.popup_error(f"Error saving file: {e}")
                    else:
                        window[log_key].print("SVG save cancelled.")
                
                # --- UR10 Control Events ---
                elif event == "-BTN_UR10_CONNECT-":
                    if ur10_controller is None or not ur10_controller.is_connected:
                        ip = values["-UR10_IP-"]
                        window["-UR10_STATUS-"].print(f"Connecting to UR10 at {ip}...")
                        ur10_controller = UR10Controller(ip)
                        if ur10_controller.connect():
                            window["-UR10_STATUS-"].print("Successfully connected.")
                            window["-BTN_UR10_CONNECT-"].update(text="Disconnect")
                            window["-BTN_START-"].update(disabled=False)
                            window["-BTN_UR10_HOME-"].update(disabled=False)
                            window["-BTN_SET_HOME-"].update(disabled=False)
                            window["-BTN_CHECK_CANVAS-"].update(disabled=False)
                            window["-BTN_PEN_CHANGE-"].update(disabled=False)
                        else:
                            window["-UR10_STATUS-"].print("Connection failed.")
                            ur10_controller = None
                    else:
                        ur10_controller.disconnect()
                        window["-UR10_STATUS-"].print("Disconnected.")
                        window["-BTN_UR10_CONNECT-"].update(text="Connect to UR10")
                        window["-BTN_START-"].update(disabled=True)
                        window["-BTN_PAUSE-"].update(disabled=True)
                        window["-BTN_STOP-"].update(disabled=True)
                        window["-BTN_UR10_HOME-"].update(disabled=True)
                        window["-BTN_SET_HOME-"].update(disabled=True)
                        window["-BTN_CHECK_CANVAS-"].update(disabled=True)
                        window["-BTN_PEN_CHANGE-"].update(disabled=True)
                        ur10_controller = None

                elif event == "-BTN_SET_HOME-":
                    if ur10_controller and ur10_controller.is_connected:
                        window["-UR10_STATUS-"].print("Getting current robot position...")
                        current_pose = ur10_controller.get_current_pose()
                        if current_pose:
                            home_pose = current_pose
                            config = { "pose": home_pose, "corner": values["-CANVAS_CORNER-"] }
                            with open("home_config.json", "w") as f: json.dump(config, f)
                            pose_str = ", ".join([f"{x:.3f}" for x in home_pose])
                            window["-HOME_POSE_DISPLAY-"].update(pose_str)
                            window["-UR10_STATUS-"].print(f"Home position set to: {pose_str}")
                        else: window["-UR10_STATUS-"].print("Failed to get current position.")
                    else: window["-UR10_STATUS-"].print("Error: Not connected to the robot.")

                elif event == "-BTN_START-":
                    if ur10_controller and ur10_controller.is_connected:
                        svg_file = values["-SVG_PATH-"]
                        if not svg_file or not os.path.exists(svg_file):
                            window["-UR10_STATUS-"].print("Error: SVG file not found.")
                            continue
                        if not home_pose:
                            window["-UR10_STATUS-"].print("Error: Home position not set.")
                            continue
                        try:
                            canvas_width_mm = float(values["-CANVAS_WIDTH-"])
                            canvas_height_mm = float(values["-CANVAS_HEIGHT-"])
                            dry_run = values["-DRY_RUN-"]
                            corner = values["-CANVAS_CORNER-"]
                            rotation_angle = values["-GLOBAL_ROTATION-"]
                            speed_control = [values["-PLOT_SPEED-"]]
                            acceleration = values["-PLOT_ACCEL-"]
                            window["-UR10_STATUS-"].print(f"Parsing SVG file: {svg_file}")
                            home_x, home_y, home_z, home_rx, home_ry, home_rz = home_pose
                            path, width, height = parse_svg(svg_file, home_x, home_y, home_z, home_rx, home_ry, home_rz, canvas_width_mm, canvas_height_mm, dry_run, corner, safe_z_offset=SAFE_Z_OFFSET, rotation_angle=rotation_angle)
                            scaled_dims["width"] = width
                            scaled_dims["height"] = height
                            if path:
                                window["-BTN_START-"].update(disabled=True)
                                window["-BTN_PAUSE-"].update(disabled=False)
                                window["-BTN_STOP-"].update(disabled=False)
                                window["-BTN_UR10_HOME-"].update(disabled=True)
                                window["-BTN_CHECK_CANVAS-"].update(disabled=True)
                                window["-BTN_PEN_CHANGE-"].update(disabled=True)
                                window["-REALTIME_GRAPH-"].erase()
                                threading.Thread(target=ur10_controller.execute_path_realtime, args=(path, home_pose, speed_control, acceleration, window, dry_run), daemon=True).start()
                            else: window["-UR10_STATUS-"].print("Error: Could not parse SVG path.")
                        except ValueError: window["-UR10_STATUS-"].print("Error: Invalid Canvas Width or Height. Please enter numbers.")
                        except Exception as e: window["-UR10_STATUS-"].print(f"An error occurred: {e}")
                    else: window["-UR10_STATUS-"].print("Error: Not connected to the robot.")

                elif event == "-DRAW_LINE-":
                    is_dither = values["-RENDER_AS_DOTS-"]
                    start_point, end_point = values[event]
                    graph_size = window["-REALTIME_GRAPH-"].CanvasSize
                    width, height = scaled_dims["width"], scaled_dims["height"]
                    corner = values["-CANVAS_CORNER-"]
                    home_x, home_y = home_pose[0], home_pose[1]
                    rotation_angle = values["-GLOBAL_ROTATION-"]
                    
                    def unrotate_point(p_rotated):
                        angle_rad = math.radians(-(rotation_angle + 45))
                        cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
                        x_r, y_r = p_rotated[0], p_rotated[1]
                        x_unrotated = home_x + (x_r - home_x) * cos_a - (y_r - home_y) * sin_a
                        y_unrotated = home_y + (x_r - home_x) * sin_a + (y_r - home_y) * cos_a
                        return (x_unrotated, y_unrotated)

                    start_unrotated, end_unrotated = unrotate_point(start_point), unrotate_point(end_point)

                    def transform_coordinates(x, y):
                        if corner == "Top Left": min_x, max_x, min_y, max_y = home_x, home_x + width, home_y - height, home_y
                        elif corner == "Top Right": min_x, max_x, min_y, max_y = home_x - width, home_x, home_y - height, home_y
                        elif corner == "Bottom Left": min_x, max_x, min_y, max_y = home_x, home_x + width, home_y, home_y + height
                        elif corner == "Bottom Right": min_x, max_x, min_y, max_y = home_x - width, home_x, home_y, home_y + height
                        else: min_x, max_x, min_y, max_y = home_x, home_x + width, home_y - height, home_y
                        
                        norm_x = (x - min_x) / (max_x - min_x) if (max_x - min_x) != 0 else 0
                        norm_y = (y - min_y) / (max_y - min_y) if (max_y - min_y) != 0 else 0
                        
                        graph_x = norm_x * graph_size[0]
                        graph_y = graph_size[1] - (norm_y * graph_size[1])
                        return graph_x, graph_y

                    if is_dither:
                        x, y = transform_coordinates(start_unrotated[0], start_unrotated[1])
                        window["-REALTIME_GRAPH-"].draw_point((x,y), size=1, color='black')
                    else:
                        x1, y1 = transform_coordinates(start_unrotated[0], start_unrotated[1])
                        x2, y2 = transform_coordinates(end_unrotated[0], end_unrotated[1])
                        window["-REALTIME_GRAPH-"].draw_line((x1, y1), (x2, y2), color='black')

                elif event == "-BTN_PAUSE-":
                    if ur10_controller and ur10_controller.is_connected:
                        if not ur10_controller.pause_event.is_set():
                            ur10_controller.pause_event.set()
                            window["-BTN_PAUSE-"].update(text="Resume")
                            window["-UR10_STATUS-"].print("Plotting paused.")
                            window["-BTN_UR10_HOME-"].update(disabled=False)
                            window["-BTN_CHECK_CANVAS-"].update(disabled=False)
                            window["-BTN_PEN_CHANGE-"].update(disabled=False)
                        else:
                            ur10_controller.pause_event.clear()
                            window["-BTN_PAUSE-"].update(text="Pause")
                            window["-UR10_STATUS-"].print("Plotting resumed.")
                            window["-BTN_UR10_HOME-"].update(disabled=True)
                            window["-BTN_CHECK_CANVAS-"].update(disabled=True)
                            window["-BTN_PEN_CHANGE-"].update(disabled=True)

                elif event == "-BTN_STOP-":
                    if ur10_controller and ur10_controller.is_connected:
                        ur10_controller.stop_event.set()
                        window["-BTN_STOP-"].update(disabled=True) 
                        window["-UR10_STATUS-"].print("Stopping plot...")

                elif event == "-BTN_UR10_HOME-":
                    if ur10_controller and ur10_controller.is_connected:
                        if home_pose:
                            window["-UR10_STATUS-"].print("Sending robot to home position...")
                            acceleration = values["-PLOT_ACCEL-"]
                            ur10_controller.go_home(home_pose, acceleration=acceleration)
                            window["-UR10_STATUS-"].print("Robot is at home.")
                        else: window["-UR10_STATUS-"].print("Error: Not connected to the robot.")
                    else: window["-UR10_STATUS-"].print("Error: Not connected to the robot.")

                elif event == "-BTN_CHECK_CANVAS-":
                    if ur10_controller and ur10_controller.is_connected:
                        if not home_pose:
                            window["-UR10_STATUS-"].print("Error: Home position not set.")
                            continue
                        try:
                            canvas_width_m, canvas_height_m = float(values["-CANVAS_WIDTH-"]) / 1000.0, float(values["-CANVAS_HEIGHT-"]) / 1000.0
                            corner, acceleration, rotation_angle = values["-CANVAS_CORNER-"], values["-PLOT_ACCEL-"], values["-GLOBAL_ROTATION-"]
                            hx, hy, hz, hrx, hry, hrz = home_pose
                            safe_z = hz + SAFE_Z_OFFSET
                            if corner == "Top Left": sequence = [(hx, hy), (hx + canvas_width_m, hy), (hx + canvas_width_m, hy - canvas_height_m), (hx, hy - canvas_height_m), (hx, hy)]
                            elif corner == "Top Right": sequence = [(hx, hy), (hx, hy - canvas_height_m), (hx - canvas_width_m, hy - canvas_height_m), (hx - canvas_width_m, hy), (hx, hy)]
                            elif corner == "Bottom Left": sequence = [(hx, hy), (hx, hy + canvas_height_m), (hx + canvas_width_m, hy + canvas_height_m), (hx + canvas_width_m, hy), (hx, hy)]
                            elif corner == "Bottom Right": sequence = [(hx, hy), (hx - canvas_width_m, hy), (hx - canvas_width_m, hy + canvas_height_m), (hx, hy + canvas_height_m), (hx, hy)]
                            angle_rad = math.radians(rotation_angle + 45)
                            cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
                            def rotate_point(p):
                                px, py = p[0], p[1]
                                x_rot = hx + (px - hx) * cos_a - (py - hy) * sin_a
                                y_rot = hy + (px - hx) * sin_a + (py - hy) * cos_a
                                return (x_rot, y_rot)
                            corners_rotated = [rotate_point(p) for p in sequence]
                            corner_poses = [(p[0], p[1], safe_z, hrx, hry, hrz) for p in corners_rotated]
                            window["-UR10_STATUS-"].print("Moving robot to check canvas corners...")
                            threading.Thread(target=ur10_controller.execute_move_sequence, args=(corner_poses, values["-PLOT_SPEED-"], acceleration), daemon=True).start()
                        except ValueError: window["-UR10_STATUS-"].print("Error: Invalid Canvas Width or Height.")
                        except Exception as e: window["-UR10_STATUS-"].print(f"An error occurred: {e}")
                    else: window["-UR10_STATUS-"].print("Error: Not connected to the robot.")

                elif event == "-BTN_PEN_CHANGE-":
                    if ur10_controller and ur10_controller.is_connected:
                        if home_pose:
                            window["-UR10_STATUS-"].print("Moving robot to pen change position...")
                            ur10_controller.go_to_pen_change_position(home_pose)
                            window["-UR10_STATUS-"].print("Robot is at pen change position.")
                        else:
                            window["-UR10_STATUS-"].print("Error: Home position not set.")
                    else:
                        window["-UR10_STATUS-"].print("Error: Not connected to the robot.")

                if 'speed_control' in locals():
                    speed_control[0] = values["-PLOT_SPEED-"]
            except Exception as e:
                print("\nAn unexpected error occurred:")
                import traceback
                traceback.print_exc()
                sg.popup_error(f"An unexpected error occurred:\n\n{e}\n\nCheck the log for details.")

    finally:
        # --- End ---
        if ur10_controller and ur10_controller.is_connected:
            ur10_controller.disconnect()
        window.close()

if __name__ == "__main__":
    main()
