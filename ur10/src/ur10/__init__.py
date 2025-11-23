import FreeSimpleGUI as sg
import vpype
from vpype_cli import execute  # Correct import for the 'execute' function

# --- NEW MATPLOTLIB IMPORTS ---
import matplotlib
matplotlib.use('Agg')  # Use the 'Agg' backend for non-GUI rendering
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
# --------------------------------

import io
import os
from PIL import Image
import threading  # <-- NEW IMPORT FOR THREADING
import time

# --- Imports for type hinting ---
from typing import Union

# --- IMPORTS FOR HATCHED ---
import hatched              # <-- IMPORT THE NEW hatched.py FILE
import cv2                  # <-- Still needed for run_hatched_thread
import numpy as np          # <-- Still needed for run_hatched_thread
# ---------------------------


# 888888888888888888888888888888888888888888888888888888888888888888888888888888
# Helper Functions (GUI)
# 888888888888888888888888888888888888888888888888888888888888888888888888888888

def update_preview(window: sg.Window, document: vpype.Document, is_cmyk: bool, max_size: tuple = (600, 600)):
    """
    Renders a vpype.Document to a PNG using Matplotlib and displays it in the GUI.
    
    :param window: The sg.Window object
    :param document: The vpype.Document to render
    :param is_cmyk: If True, render with CMYK colors. If False, render all black.
    :param max_size: The max dimensions of the preview image
    """
    
    # 1. Create a matplotlib Figure and Axes
    dpi = 100
    fig = Figure(figsize=(max_size[0] / dpi, max_size[1] / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1]) # Use full figure area
    ax.axis('off') # Hide the axes
    ax.set_facecolor('white')
    fig.set_facecolor('white')

    if document is None or document.is_empty():
        pass

    else:
        try:
            # 2. Get bounds and set plot limits
            bounds = document.bounds()
            if bounds:
                min_x, min_y, max_x, max_y = bounds
                ax.set_xlim(min_x, max_x)
                ax.set_ylim(min_y, max_y)
                ax.invert_yaxis()
            
            color_map = { 1: 'cyan', 2: 'magenta', 3: 'yellow', 4: 'black' }

            # 3. Plot every line from the document
            for layer_id, line_collection in document.layers.items():
                
                # --- MODIFIED LOGIC ---
                color = 'black' # Default to black
                if is_cmyk:
                    # If CMYK is checked, try to get the layer color
                    color = color_map.get(layer_id, 'black')
                # --- END MODIFIED LOGIC ---
                
                for line in line_collection:
                    x_data = [p.real for p in line]
                    y_data = [p.imag for p in line]
                    ax.plot(x_data, y_data, color=color, linewidth=0.5)

        except Exception as e:
            print(f"Error during Matplotlib rendering: {e}")
            pass

    # 4. Render the figure to a PNG buffer
    try:
        canvas = FigureCanvas(fig)
        canvas.draw()
        buf = canvas.buffer_rgba()
        img = Image.frombytes("RGBA", canvas.get_width_height(), buf)
        png_buffer = io.BytesIO()
        img.save(png_buffer, format="PNG")
        
        # 5. Update the GUI
        window["-VISUAL-"].update(data=png_buffer.getvalue())

    except Exception as e:
        print(f"Error saving Matplotlib canvas to PNG: {e}")
        img = Image.new('RGB', max_size, color='white')
        bio = io.BytesIO()
        img.save(bio, format='PNG')
        window["-VISUAL-"].update(data=bio.getvalue())

# 888888888888888888888888888888888888888888888888888888888888888888888888888888
# Threading Functions
# 888888888888888888888888888888888888888888888888888888888888888888888888888888

def run_vectorize_thread(window: sg.Window, cmd_string: str, is_cmyk: bool):
    """
    Runs the long 'execute' command in a separate thread and sends an
    event back to the main GUI loop when finished.
    """
    try:
        print(f"Running command: vpype {cmd_string}")
        start_time = time.time()
        document = execute(cmd_string)
        end_time = time.time()
        print(f"Vectorization complete in {end_time - start_time:.2f} seconds.")
        
        # Send an event to the main thread with the result
        # Pass the is_cmyk flag back to the main thread
        window.write_event_value("-THREAD_DONE-", (document, None, is_cmyk))
        
    except Exception as e:
        print("An error occurred in the vectorization thread:")
        import traceback
        traceback.print_exc()
        # Send the error message back
        window.write_event_value("-THREAD_DONE-", (None, str(e), False))


def run_hatched_thread(window: sg.Window, params: dict):
    """
    Runs the 'hatch' function in a separate thread and sends the
    resulting document back to the main GUI loop.
    
    ---
    This is a breakdown of the `hatched.hatch()` function for better debugging.
    ---
    """
    try:
        print("Running local hatch function...") # <-- USER SAW THIS
        start_time = time.time()
        
        # --- Manually execute the logic from hatched.hatch() ---
        
        # 1. Load the image
        print("Hatch thread: Loading image...")
        img = hatched._load_image(
            file_path=params["img_path"],
            blur_radius=int(params["blur"]),
            image_scale=params["image_scale"], # <-- USE THE NEW PARAMETER
            interpolation=cv2.INTER_LINEAR, # Not in GUI
            h_mirror=False, # Not in GUI
            invert=params["invert"],
        )
        print(f"Hatch thread: Image loaded. Shape: {img.shape}") # <-- This will now be smaller

        # 2. Build the hatch patterns (This is the slow part)
        print("Hatch thread: Building hatch patterns (this may take a while)...")
        mls, *cnts = hatched._build_hatch(
            img,
            hatch_pitch=params["pitch"],
            levels=params["levels"],
            invert=params["invert"],
            circular=params["circular"],
            hatch_angle=params["angle"],
            offset=0.0, # Not in GUI
            center=(0.5, 0.5), # Not in GUI
        )
        print("Hatch thread: Hatch patterns built.")
        
        # 3. Convert shapely.MultiLineString to vpype.Document
        print("Hatch thread: Converting lines to vpype document...")
        document = vpype.Document()
        
        # Handle CMYK case
        if params["cmyk"]:
            # TODO: The local hatch function doesn't seem to support CMYK natively.
            # It returns a single MultiLineString.
            # For now, we will just put this on layer 1.
            print("Warning: Local hatch CMYK not fully implemented. Placing on layer 1.")
            lines = []
            if mls:
                for line_string in mls.geoms:
                    # Convert coords to complex numbers
                    # --- FIX: Use np.ascontiguousarray to fix ValueError ---
                    lines.append(np.ascontiguousarray(line_string.coords).view(np.complex128).reshape(-1))
            document.add(vpype.LineCollection(lines), layer_id=1)
        
        else:
            # Handle non-CMYK case (contours)
            if params["lines"]:
                print("Hatch thread: Processing contours...")
                contour_lines = []
                for cnt_level in cnts:
                    for cnt in cnt_level:
                        # Convert (row, col) to (x, y) and swap
                        # --- FIX: Use np.ascontiguousarray to fix ValueError ---
                        contour_lines.append(np.ascontiguousarray(cnt[:, [1, 0]]).view(np.complex128).reshape(-1))
                document.add(vpype.LineCollection(contour_lines), layer_id=1)
                print("Hatch thread: Contours added.")

            # Handle non-CMYK case (hatches)
            if params["hatch"]:
                print("Hatch thread: Processing hatches...")
                lines = []
                if mls:
                    for line_string in mls.geoms:
                        # Convert coords to complex numbers
                        # --- FIX: Use np.ascontiguousarray to fix ValueError ---
                        lines.append(np.ascontiguousarray(line_string.coords).view(np.complex128).reshape(-1))
                document.add(vpype.LineCollection(lines), layer_id=2 if params["lines"] else 1)
                print("Hatch thread: Hatches added.")
        
        end_time = time.time()
        print(f"Hatch processing complete in {end_time - start_time:.2f} seconds.")
        
        window.write_event_value("-THREAD_DONE-", (document, None, params["cmyk"]))

    except Exception as e:
        print("An error occurred in the hatch thread:")
        import traceback
        traceback.print_exc()
        window.write_event_value("-THREAD_DONE-", (None, str(e), False))


# 888888888888888888888888888888888888888888888888888888888888888888888888888888
# GUI Layout
# 888888888888888888888888888888888888888888888888888888888888888888888888888888

def create_layout():
    """
    Creates the main GUI layout.
    """
    
    sg.theme("DarkGrey2")
    
    # --- Tab 1: Flow Imager ---
    flow_controls = [
        [sg.Text("Vectorize an image using 'flow_imager'.", font="Helvetica 12")],
        [sg.HorizontalSeparator()],
        [sg.Text("Source Image:", s=(15, 1)), sg.Input(key="-IMG_PATH_FLOW-", s=(30, 1)), sg.FileBrowse(target="-IMG_PATH_FLOW-")],
        
        [sg.Text("Noise Coeff:", s=(15, 1)), sg.Input("0.01", key="-FLOW_NOISE-", s=(10, 1))],
        [sg.Text("Min Separation:", s=(15, 1)), sg.Slider(range=(0.5, 10), default_value=0.8, resolution=0.1, orientation="h", key="-FLOW_MIN_SEP-", s=(30, 20))],
        [sg.Text("Max Separation:", s=(15, 1)), sg.Slider(range=(1, 20), default_value=10.0, resolution=0.1, orientation="h", key="-FLOW_MAX_SEP-", s=(30, 20))],
        
        [sg.Text("Min Length (mm):", s=(15, 1)), sg.Input("0", key="-FLOW_MIN_LEN-", s=(10, 1))],
        [sg.Text("Max Length (mm):", s=(15, 1)), sg.Input("1000", key="-FLOW_MAX_LEN-", s=(10, 1))],
        [sg.Text("Max Size (px):", s=(15, 1)), sg.Input("1600", key="-FLOW_MAX_SIZE-", s=(10, 1))],
        
        [sg.Text("N Fields:", s=(15, 1)), sg.Slider(range=(1, 10), default_value=1, resolution=1, orientation="h", key="-FLOW_N_FIELDS-", s=(30, 20))],
        [sg.Text("Edge Flow:", s=(15, 1)), sg.Slider(range=(0.0, 10.0), default_value=1.0, resolution=0.1, orientation="h", key="-FLOW_EDGE-", s=(30, 20))],
        [sg.Text("Dark Flow:", s=(15, 1)), sg.Slider(range=(0.0, 10.0), default_value=1.0, resolution=0.1, orientation="h", key="-FLOW_DARK-", s=(30, 20))],
        [sg.Text("Rotate:", s=(15, 1)), sg.Slider(range=(0, 360), default_value=0, resolution=1, orientation="h", key="-FLOW_ROTATE-", s=(30, 20))],
        
        [
            sg.Checkbox("Use CMYK Layers", key="-FLOW_CMYK-", default=False),
            sg.Checkbox("K-d Tree (`-kdt`)", key="-FLOW_KDT-", default=False),
            sg.Checkbox("Trim Border (`-tm`)", key="-FLOW_TRIM-", default=False),
        ],
        [sg.Button("Vectorize with Flow Imager", key="-BTN_VECTORIZE_FLOW-", expand_x=True, font="Helvetica 10 bold")],
    ]

    # --- Tab 2: Hatched ---
    hatched_controls = [
        [sg.Text("Vectorize an image using local 'hatched.py'.", font="Helvetica 12")],
        [sg.HorizontalSeparator()],
        [sg.Text("Source Image:", s=(15, 1)), sg.Input(key="-IMG_PATH_HATCHED-", s=(30, 1)), sg.FileBrowse(target="-IMG_PATH_HATCHED-")],
        
        # --- NEW: Image Scale Slider ---
        [sg.Text("Image Scale:", s=(15, 1)), sg.Slider(range=(0.1, 1.0), default_value=0.5, resolution=0.05, orientation="h", key="-HATCHED_SCALE-", s=(30, 20))],
        
        [sg.Text("Hatch Angles:", s=(15, 1)), sg.Input("45", key="-HATCHED_ANGLES-", s=(15, 1)), sg.Text("Space-separated (e.g. 0 45 90)")],
        [sg.Text("Hatch Pitch (px):", s=(15, 1)), sg.Slider(range=(1.0, 20.0), default_value=5.0, resolution=0.1, orientation="h", key="-HATCHED_PITCH-", s=(30, 20))],
        [sg.Text("Gaussian Blur (px):", s=(15, 1)), sg.Slider(range=(0.0, 20.0), default_value=1.0, resolution=0.1, orientation="h", key="-HATCHED_BLUR-", s=(30, 20))],
        
        [sg.Text("Levels:", s=(15, 1)), sg.Input("64 128 192", key="-HATCHED_LEVELS-", s=(15, 1)), sg.Text("Space-separated (0-255)")],
        
        [
            sg.Checkbox("Use CMYK Layers", key="-HATCHED_CMYK-", default=False),
            sg.Checkbox("Invert", key="-HATCHED_INVERT-", default=False),
            sg.Checkbox("Circular Hatch", key="-HATCHED_CIRCULAR-", default=False),
        ],
        [
            sg.Checkbox("Draw Contours", key="-HATCHED_LINES-", default=True),
            sg.Checkbox("Draw Hatch Fill", key="-HATCHED_HATCH-", default=True),
        ],
        [sg.Button("Vectorize with Hatched", key="-BTN_VECTORIZE_HATCHED-", expand_x=True, font="Helvetica 10 bold")],
    ]

    # --- Main Controls Column ---
    controls_column = [
        [sg.Text("Vpype GUI", font="Helvetica 18 bold", pad=((0,0), (0, 10)))],
        
        [sg.TabGroup([
            [
                sg.Tab("Flow Imager", flow_controls, key="-TAB_FLOW-"),
                sg.Tab("Hatched", hatched_controls, key="-TAB_HATCHED-")
            ]
        ], key="-TABGROUP-", expand_x=True)],

        [sg.Text("Processing... please wait.", key="-LOADING-", visible=False, font="Helvetica 10 bold", text_color="yellow", justification="center", expand_x=True)],
        
        [sg.HorizontalSeparator(pad=((0,0), (10, 10)))],
        [sg.Text("Optimization", font="Helvetica 12")],
        [sg.Text("Merge Tol. (mm):", s=(15, 1)), sg.Input("0.1", key="-OPT_MERGE-", s=(10, 1))],
        [sg.Text("Simplify Tol. (mm):", s=(15, 1)), sg.Input("0.05", key="-OPT_SIMPLIFY-", s=(10, 1))],
        [sg.Button("Optimize Drawing", key="-BTN_OPTIMIZE-", expand_x=True)],
        [sg.HorizontalSeparator(pad=((0,0), (10, 10)))],
        
        [sg.Button("Save SVG", key="-BTN_SAVE-", expand_x=True, button_color=("white", "green"))]
    ]

    visual_column = [
        [sg.Text("Preview", font="Helvetica 18 bold", pad=((0,0), (0, 10)))],
        [
            sg.Graph(
                canvas_size=(600, 600),
                graph_bottom_left=(0, 600),
                graph_top_right=(600, 0),
                key="-GRAPH-",
                background_color="white",
                enable_events=True
            )
        ],
        [sg.Image(key="-VISUAL-", size=(600, 600), background_color="white")]
    ]
    
    layout = [
        [
            sg.Column(controls_column, vertical_alignment="top"),
            sg.VSeparator(),
            sg.Column(visual_column, vertical_alignment="top", element_justification="center")
        ],
        [sg.HorizontalSeparator()],
        [
            sg.Text("Log Output:"),
            sg.Multiline(
                key="-LOG-", 
                size=(100, 10), 
                font="Courier 10", 
                autoscroll=True, 
                disabled=True,
                # reroute_stdout=True, # We leave this off to see logs in console
                # reroute_stderr=True
            )
        ]
    ]
    
    return layout

# 888888888888888888888888888888888888888888888_8888888888888888888888888888888
# Main Application Logic
# 888888888888888888888888888888888888888888888_8888888888888888888888888888888

def main():
    """
    Main event loop for the application.
    """
    
    layout = create_layout()
    window = sg.Window("Vpype GUI", layout, finalize=True, resizable=True)
    
    window["-GRAPH-"].hide_row()
    document: Union[vpype.Document, None] = None
    update_preview(window, None, is_cmyk=False) # Pass default CMYK flag

    # --- Event Loop ---
    while True:
        event, values = window.read()

        if event == sg.WIN_CLOSED:
            break
        
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
                    
                if n_fields != 1:
                    cmd_string += f" -nf {n_fields}"
                    
                try:
                    min_len = float(min_len_str)
                    if min_len > 0:
                        cmd_string += f" -ml {min_len}mm"
                except ValueError:
                    print(f"Ignoring invalid Min Length: {min_len_str}")

                try:
                    max_len = float(max_len_str)
                    if max_len > 0:
                        cmd_string += f" -Ml {max_len}mm"
                except ValueError:
                    print(f"Ignoring invalid Max Length: {max_len_str}")

                try:
                    max_size = int(max_size_str)
                    if max_size > 0:
                        cmd_string += f" --max_size {max_size}"
                except ValueError:
                    print(f"Ignoring invalid Max Size: {max_size_str}")

                if edge_flow != 1.0:
                    cmd_string += f" -efm {edge_flow}"
                
                if dark_flow != 1.0:
                    cmd_string += f" -dfm {dark_flow}"
                
                if rotate != 0:
                    cmd_string += f" --rotate {rotate}"
                
                if cmyk:
                    cmd_string += " --cmyk"
                
                if kdt:
                    cmd_string += " -kdt"
                
                if trim:
                    cmd_string += " -tm"
                
                cmd_string += f" \"{img_path}\""
                
                # --- NEW THREADING LOGIC ---
                # 1. Disable buttons and show loading text
                window["-BTN_VECTORIZE_FLOW-"].update(disabled=True)
                window["-BTN_VECTORIZE_HATCHED-"].update(disabled=True)
                window["-BTN_OPTIMIZE-"].update(disabled=True)
                window["-LOADING-"].update(visible=True)
                
                # 2. Start the worker thread
                threading.Thread(
                    target=run_vectorize_thread,
                    args=(window, cmd_string, cmyk), # Pass the CMYK flag
                    daemon=True
                ).start()
                # -----------------------------
            
            # --- NEW: Hatched Vectorize Event ---
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
                params["image_scale"] = values["-HATCHED_SCALE-"] # <-- Get the new scale
                
                # Parse angles
                try:
                    angles = [float(a) for a in values["-HATCHED_ANGLES-"].strip().split()]
                    if not angles:
                        angles = [45.0] # Default if empty
                    params["angle"] = angles[0] # Local hatch only supports one angle
                    if len(angles) > 1:
                        print(f"Warning: Local hatch only supports one angle. Using {angles[0]}.")
                except ValueError:
                    print(f"Invalid Hatch Angles: {values['-HATCHED_ANGLES-']}. Using 45.")
                    params["angle"] = 45.0

                # Parse levels
                try:
                    levels = [int(level_str) for level_str in values["-HATCHED_LEVELS-"].strip().split() if 0 < int(level_str) < 255]
                    if not levels:
                        levels = (64, 128, 192) # Default if empty
                    params["levels"] = tuple(levels)
                except ValueError:
                    print(f"Invalid Levels: {values['-HATCHED_LEVELS-']}. Using defaults.")
                    params["levels"] = (64, 128, 192)

                
                # --- THREADING LOGIC ---
                window["-BTN_VECTORIZE_FLOW-"].update(disabled=True)
                window["-BTN_VECTORIZE_HATCHED-"].update(disabled=True)
                window["-BTN_OPTIMIZE-"].update(disabled=True)
                window["-LOADING-"].update(visible=True)
                
                threading.Thread(
                    target=run_hatched_thread, # <-- Call the NEW thread function
                    args=(window, params),      # <-- Pass the parsed params dict
                    daemon=True
                ).start()

            # --- NEW: Event for when the thread is done ---
            elif event == "-THREAD_DONE-":
                # 1. Get results from the event
                doc_from_thread, error_message, is_cmyk = values[event]
                
                # 2. Re-enable buttons and hide loading text
                window["-BTN_VECTORIZE_FLOW-"].update(disabled=False)
                window["-BTN_VECTORIZE_HATCHED-"].update(disabled=False)
                window["-BTN_OPTIMIZE-"].update(disabled=False)
                window["-LOADING-"].update(visible=False)
                
                # 3. Handle results
                if error_message:
                    print(f"Thread Error: {error_message}")
                    sg.popup_error(f"Vectorization Failed:\n\n{error_message}")
                elif doc_from_thread:
                    document = doc_from_thread  # Store the new document
                    print("Thread finished. Updating preview.")
                    # Pass the checkbox value to the preview function
                    update_preview(window, document, is_cmyk=is_cmyk)
                else:
                    print("Thread finished but document is empty.")
                    document = None # Clear the old document
                    update_preview(window, None, is_cmyk=False) # Show a blank screen
            
            # --- Optimize Event ---
            elif event == "-BTN_OPTIMIZE-":
                if document is None:
                    print("No drawing to optimize. Generate or vectorize first.")
                    continue
                
                print("Optimizing drawing...")
                
                merge_tol = values["-OPT_MERGE-"].strip().replace("mm", "").strip()
                simplify_tol = values["-OPT_SIMPLIFY-"].strip().replace("mm", "").strip()
                
                cmd_string = f"linemerge -t {merge_tol}mm linesimplify -t {simplify_tol}mm linesort"
                
                print(f"Running command: vpype {cmd_string}")
                # This is fast, so no thread is needed
                document = execute(cmd_string, document=document)
                
                if document:
                    print("Optimization complete. Updating preview.")
                    
                    # Check which tab is active to get the right CMYK value
                    active_tab_key = values["-TABGROUP-"]
                    is_cmyk = False
                    if active_tab_key == "-TAB_FLOW-":
                        is_cmyk = values["-FLOW_CMYK-"]
                    elif active_tab_key == "-TAB_HATCHED-":
                        is_cmyk = values["-HATCHED_CMYK-"]
                        
                    update_preview(window, document, is_cmyk=is_cmyk)
                else:
                    print("Optimization failed.")

            # --- Save Event ---
            elif event == "-BTN_SAVE-":
                if document is None:
                    print("Error: No document to save. Generate or vectorize first.")
                    continue

                save_path = sg.popup_get_file(
                    "Save As",
                    save_as=True,
                    no_window=True,
                    default_extension=".svg",
                    file_types=(("SVG Files", "*.svg"),)
                )

                if save_path:
                    try:
                        print(f"Saving to {save_path}...")
                        with open(save_path, "w", encoding="utf-8") as f:
                            vpype.write_svg(f, document)
                        print("File saved successfuly.")
                    except Exception as e:
                        print(f"Error saving file: {e}")
                        sg.popup_error(f"Error saving file: {e}")
                else:
                    print("Save cancelled.")

        except Exception as e:
            print("\nAn unexpected error occurred:")
            import traceback
            traceback.print_exc()
            sg.popup_error(f"An unexpected error occurred:\n\n{e}\n\nCheck the log for details.")

    # --- End ---
    window.close()

# 888888888888888888888888888888888S88888888888888888888888888888888888888888888
# Run the application
# 888888888888888888888888888888888888888888888888888888888888888888888888888888
if __name__ == "__main__":
    main()