import FreeSimpleGUI as sg
import vpype
import hatched
import numpy as np
import time
import traceback

def run_hatched_thread(window: sg.Window, params: dict, stop_event: "threading.Event"):
    """
    Runs the 'hatch' function in a separate thread and sends the
    resulting document back to the main GUI loop.
    """
    try:
        window.write_event_value("-LOG_MESSAGE-", "Starting Hatched vectorization...")
        print("Running local hatch function...") 
        start_time = time.time()
        
        # 1. Load the image
        window.write_event_value("-LOG_MESSAGE-", "Loading image...")
        print("Hatch thread: Loading image...")
        img = hatched._load_image(
            file_path=params["img_path"],
            blur_radius=int(params["blur"]),
            image_scale=params["image_scale"],
            interpolation=params["interpolation"],
            h_mirror=params["h_mirror"],
            invert=params["invert"],
        )
        print(f"Hatch thread: Image loaded. Shape: {img.shape}") 

        # 2. Build the hatch patterns (This is the slow part)
        window.write_event_value("-LOG_MESSAGE-", "Building hatch patterns (this may take a while)...")
        print("Hatch thread: Building hatch patterns (this may take a while)...")
        mls, *cnts = hatched._build_hatch(
            img,
            hatch_pitch=params["pitch"],
            levels=params["levels"],
            invert=params["invert"],
            circular=params["circular"],
            center=params["center"],
            hatch_angle=params["angle"],
            offset=params["offset"],
            stop_event=stop_event,
        )
        print("Hatch thread: Hatch patterns built.")
        
        # 3. Convert shapely.MultiLineString to vpype.Document
        window.write_event_value("-LOG_MESSAGE-", "Converting lines to vpype document...")
        print("Hatch thread: Converting lines to vpype document...")
        document = vpype.Document()
        
        # Handle CMYK case
        if params["cmyk"]:
            # The local hatch function doesn't support CMYK natively.
            # It returns a single MultiLineString.
            # For now, we will just put this on layer 1.
            window.write_event_value("-LOG_MESSAGE-", "Warning: Local hatch CMYK not fully implemented. Placing on layer 1.")
            print("Warning: Local hatch CMYK not fully implemented. Placing on layer 1.")
            lines = []
            if mls:
                for line_string in mls.geoms:
                    # Convert coords to complex numbers
                    lines.append(np.ascontiguousarray(line_string.coords).view(np.complex128).reshape(-1))
            document.add(vpype.LineCollection(lines), layer_id=1)
        
        else:
            # Handle non-CMYK case (contours)
            if params["lines"]:
                window.write_event_value("-LOG_MESSAGE-", "Processing contours...")
                print("Hatch thread: Processing contours...")
                contour_lines = []
                # cnts is a list of lists of contours, one list per level
                for cnt_level in cnts:
                    if stop_event.is_set():
                        raise InterruptedError("Hatched process stopped by user")
                    for cnt in cnt_level:
                        # Convert (row, col) to (x, y) and swap
                        contour_lines.append(np.ascontiguousarray(cnt[:, [1, 0]]).view(np.complex128).reshape(-1))
                document.add(vpype.LineCollection(contour_lines), layer_id=1)
                print("Hatch thread: Contours added.")

            # Handle non-CMYK case (hatches)
            if params["hatch"]:
                window.write_event_value("-LOG_MESSAGE-", "Processing hatches...")
                print("Hatch thread: Processing hatches...")
                lines = []
                if mls:
                    if stop_event.is_set():
                        raise InterruptedError("Hatched process stopped by user")
                    for line_string in mls.geoms:
                        # Convert coords to complex numbers
                        lines.append(np.ascontiguousarray(line_string.coords).view(np.complex128).reshape(-1))
                document.add(vpype.LineCollection(lines), layer_id=2 if params["lines"] else 1)
                print("Hatch thread: Hatches added.")
        
        end_time = time.time()
        window.write_event_value("-LOG_MESSAGE-", f"Hatched vectorization complete in {end_time - start_time:.2f} seconds.")
        print(f"Hatch processing complete in {end_time - start_time:.2f} seconds.")
        
        window.write_event_value("-THREAD_DONE-", (document, "Hatched vectorization complete.", params["cmyk"]))

    except InterruptedError as e:
        print(f"Hatch thread interrupted: {e}")
        window.write_event_value("-THREAD_DONE-", (None, "Hatched vectorization stopped.", False))
    except Exception as e:
        print("An error occurred in the hatch thread:")
        traceback.print_exc()
        window.write_event_value("-THREAD_DONE-", (None, str(e), False))
