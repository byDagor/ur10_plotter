import FreeSimpleGUI as sg
import vpype as vp
from vpype_cli import execute
import numpy as np
import threading
import time
import traceback
from PIL import Image 
import random
import os
import multiprocessing
import tempfile


# This class acts as a shim for dither.py's `Plot` object.
class DitherPlotter:
    def __init__(self):
        self.plot_size = 6  # dither.py sets this to 6
        self.points = []

    def setup(self):
        """Clears any previous points."""
        self.points = []

    def dot(self, x, y):
        """Stores a point to be plotted."""
        self.points.append((x, y))

    def get_document(self, dot_radius_mm=0.0001, num_segments=8):
        """
        Converts the stored points into a vpype.Document.
        Each dot is represented as a small circle (polygon).
        """
        if not self.points:
            return vp.Document()

        all_circle_lines = []
        for x, y in self.points:
            # Manually create the points for a circle polygon
            angles = np.linspace(0, 2 * np.pi, num_segments, endpoint=False)
            circle_points = [complex(x + dot_radius_mm * np.cos(a), y + dot_radius_mm * np.sin(a)) for a in angles]
            # Close the circle
            circle_points.append(circle_points[0])
            all_circle_lines.append(np.array(circle_points))

        lc = vp.LineCollection(all_circle_lines)
        doc = vp.Document()
        doc.add(lc)
        return doc

# Now the run_dither_thread function
def _dither_task(params: dict, result_queue: multiprocessing.Queue):
    """
    The actual dithering task that runs in a separate process.
    This version uses a stochastic dithering algorithm.
    """
    try:
        img_path = params["img_path"]
        dot_radius_mm = params["dot_radius_mm"]
        image_scale = params.get("image_scale", 0.5)
        density = params.get("density", 1.0)

        dither_plotter = DitherPlotter()
        dither_plotter.setup() 

        img = Image.open(img_path).convert("L") # Convert to grayscale/luminance
        
        # Resize image based on scale
        new_width = round(img.width * image_scale)
        new_height = round(img.height * image_scale)
        img = img.resize((new_width, new_height))

        norm_dim = max(new_width, new_height)
        pixels = list(img.getdata())
        
        for i, brightness in enumerate(pixels):
            # The `darkness` is 255 - brightness.
            # We compare the amplified darkness to a random number.
            darkness = 255 - brightness
            
            # Divide by scale^2 to make the final dot density independent of the scale.
            # Scale controls the resolution, Density controls the final output darkness.
            # Add a small epsilon to avoid division by zero, although slider min is 0.1.
            check_val = (darkness * density) / ((image_scale * image_scale) + 0.001)

            if check_val > random.randint(0, 255):
                # This is a dot
                c = i % new_width
                r = i // new_width
                
                # Normalize coordinates to a 100x100 space
                x = (c/norm_dim) * 100 + random.uniform(-0.05, 0.05)
                y = (r/norm_dim) * 100 + random.uniform(-0.05, 0.05)
                dither_plotter.dot(x, y)
        
        document = dither_plotter.get_document(dot_radius_mm=dot_radius_mm)

        if document and not document.is_empty():
            # Save the document to a temporary file
            fd, temp_path = tempfile.mkstemp(suffix=".svg")
            os.close(fd)
            with open(temp_path, "w", encoding="utf-8") as f:
                vp.write_svg(f, document)
            result_queue.put((True, temp_path))
        else:
            result_queue.put((False, "Dithering resulted in an empty document."))

    except Exception as e:
        result_queue.put((False, str(e)))


def run_dither_thread(window: sg.Window, params: dict, stop_event: "threading.Event"):
    """
    This function runs in a thread and manages a separate process for the
    actual dithering work. This allows the work to be terminated and avoids GIL issues.
    """
    result_queue = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=_dither_task,
        args=(params, result_queue)
    )

    try:
        window.write_event_value("-LOG_MESSAGE-", "Starting Dither vectorization process...")
        start_time = time.time()
        
        process.start()

        # Poll for completion or stop signal
        while process.is_alive():
            if stop_event.is_set():
                print("Stop event received, terminating process.")
                process.terminate()
                process.join(timeout=1) # Attempt to gracefully join
                if process.is_alive():
                    print("Process did not terminate, killing.")
                    process.kill() # Force kill if terminate fails
                    process.join() # Wait for the kill
                return 
            
            time.sleep(0.1)

        # Process finished without being stopped
        end_time = time.time()
        window.write_event_value("-LOG_MESSAGE-", f"Dither process complete in {end_time - start_time:.2f} seconds.")

        # Get the result from the queue
        success, result_path_or_msg = result_queue.get()

        if success:
            temp_path = result_path_or_msg
            window.write_event_value("-LOG_MESSAGE-", "Loading document from temp file...")
            document = execute(f'read "{temp_path}"')
            try:
                os.remove(temp_path)
            except OSError as e:
                print(f"Error removing temp file {temp_path}: {e}")
            
            window.write_event_value("-THREAD_DONE-", (document, "Dither vectorization complete.", False))
        else:
            error_message = result_path_or_msg
            print(f"An error occurred in the dither process: {error_message}")
            window.write_event_value("-THREAD_DONE-", (None, error_message, False))

    except Exception as e:
        print("An error occurred in the dither thread wrapper:")
        traceback.print_exc()
        if process.is_alive():
            process.kill()
            process.join()
        window.write_event_value("-THREAD_DONE-", (None, str(e), False))
    finally:
        result_queue.close()
        result_queue.join_thread()

