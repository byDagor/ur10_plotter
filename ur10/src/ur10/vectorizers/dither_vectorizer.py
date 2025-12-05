import FreeSimpleGUI as sg
import vpype as vp
from vpype_cli import execute
import numpy as np
import threading
import time
import traceback
from PIL import Image, ImageEnhance
import random
import os
import multiprocessing
import tempfile

class DitherVectorizer:
    def __init__(self, image_path: str, dither_method: str, contrast_factor: float = 1.0, density: float = 1.0, h_dots: int = 150, dot_radius_mm: float = 0.175):
        self.image_path = image_path
        self.dither_method = dither_method
        self.contrast_factor = contrast_factor
        self.density = density
        self.h_dots = h_dots
        self.dot_radius_mm = dot_radius_mm
        self.points = []

    def run(self):
        # --- Image Preparation ---
        img = Image.open(self.image_path).convert("L") # Convert to grayscale
        original_width, original_height = img.size
        
        aspect_ratio = original_height / original_width
        new_width = self.h_dots
        new_height = round(new_width * aspect_ratio)
        img = img.resize((new_width, new_height))

        # --- Dithering ---
        if self.dither_method == "Floyd-Steinberg":
            self.fs_dither(img, new_width, new_height)
        elif self.dither_method == "Ordered (Halftone)":
            self.ordered_dither(img, new_width, new_height)
        elif self.dither_method == "Stochastic (Random)":
            self.random_dither(img, new_width, new_height)
        
        # --- SVG Generation ---
        return self.get_document()

    def fs_dither(self, img, new_width, new_height):
        # Apply contrast enhancement
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(self.contrast_factor)

        # Use a standard list of lists for pixels
        flat_data = list(img.getdata())
        pixels = [flat_data[i * new_width:(i + 1) * new_width] for i in range(new_height)]

        for y in range(new_height):
            for x in range(new_width):
                old_pixel = pixels[y][x]
                # A fixed threshold is fine after contrast adjustment
                new_pixel = 255 if old_pixel > 127 else 0
                pixels[y][x] = new_pixel
                
                error = old_pixel - new_pixel

                # Distribute error with boundary checking
                if x + 1 < new_width:
                    pixels[y][x + 1] += error * 7 / 16
                if x - 1 >= 0 and y + 1 < new_height:
                    pixels[y + 1][x - 1] += error * 3 / 16
                if y + 1 < new_height:
                    pixels[y + 1][x] += error * 5 / 16
                if x + 1 < new_width and y + 1 < new_height:
                    pixels[y + 1][x + 1] += error * 1 / 16

        # Generate points from the dithered data
        norm_dim = max(new_width, new_height)
        for y in range(new_height):
            for x in range(new_width):
                if pixels[y][x] == 0:
                    px = (x / norm_dim) * 100 + random.uniform(-0.05, 0.05)
                    py = (y / norm_dim) * 100 + random.uniform(-0.05, 0.05)
                    self.points.append((px, py))

    def ordered_dither(self, img, new_width, new_height):
        pixels = np.array(img, dtype=np.float32)
        norm_dim = max(new_width, new_height)
        bayer_matrix = np.array([
            [0, 128, 32, 160],
            [192, 64, 224, 96],
            [48, 176, 16, 144],
            [240, 112, 208, 80]
        ])
        for r in range(new_height):
            for c in range(new_width):
                bayer_threshold = bayer_matrix[r % 4, c % 4]
                adjusted_brightness = pixels[r, c] / (self.density + 0.001)
                if adjusted_brightness < bayer_threshold:
                    x = (c / norm_dim) * 100 + random.uniform(-0.05, 0.05)
                    y = (r / norm_dim) * 100 + random.uniform(-0.05, 0.05)
                    self.points.append((x,y))

    def random_dither(self, img, new_width, new_height):
        pixels = list(img.getdata())
        norm_dim = max(new_width, new_height)
        for i, brightness in enumerate(pixels):
            darkness = 255 - brightness
            if (darkness * self.density) > random.randint(0, 255):
                c = i % new_width
                r = i // new_width
                x = (c / norm_dim) * 100 + random.uniform(-0.05, 0.05)
                y = (r / norm_dim) * 100 + random.uniform(-0.05, 0.05)
                self.points.append((x,y))

    def get_document(self, num_segments=8):
        if not self.points:
            return vp.Document()

        all_circle_lines = []
        for x, y in self.points:
            angles = np.linspace(0, 2 * np.pi, num_segments, endpoint=False)
            circle_points = [complex(x + self.dot_radius_mm * np.cos(a), y + self.dot_radius_mm * np.sin(a)) for a in angles]
            circle_points.append(circle_points[0])
            all_circle_lines.append(np.array(circle_points))

        lc = vp.LineCollection(all_circle_lines)
        doc = vp.Document()
        doc.add(lc)
        return doc

def _dither_task(params: dict, result_queue: multiprocessing.Queue):
    """
    The actual dithering task that runs in a separate process.
    """
    try:
        vectorizer = DitherVectorizer(
            image_path=params["img_path"],
            dither_method=params.get("method", "Floyd-Steinberg"),
            contrast_factor=params.get("contrast_factor", 1.0),
            density=params.get("density", 1.0),
            h_dots=params.get("h_dots", 150),
            dot_radius_mm=params.get("dot_radius_mm", 0.175)
        )
        document = vectorizer.run()

        if document and not document.is_empty():
            # Use a temporary file to pass the document back
            fd, temp_path = tempfile.mkstemp(suffix=".svg")
            os.close(fd)
            with open(temp_path, "w", encoding="utf-8") as f:
                vp.write_svg(f, document)
            result_queue.put((True, temp_path))
        else:
            result_queue.put((False, "Dithering resulted in an empty document."))

    except Exception as e:
        traceback.print_exc()
        result_queue.put((False, str(e)))

def run_dither_thread(window: sg.Window, params: dict, stop_event: "threading.Event"):
    """
    This function runs in a thread and manages a separate process for the
    actual dithering work. This allows the work to be terminated and avoids GIL issues.
    """
    # Log the parameters being used
    param_str = (
        f"Method: {params.get('method')}, "
        f"H-Dots: {params.get('h_dots')}, "
        f"Pen Diameter: {params.get('pen_diameter_mm')}mm, "
    )
    if params.get('method') == "Floyd-Steinberg":
        param_str += f"Contrast: {params.get('contrast_factor')}"
    else:
        param_str += f"Density: {params.get('density')}"
    
    window.write_event_value("-LOG_MESSAGE-", f"Dithering with params: {param_str}")

    result_queue = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=_dither_task,
        args=(params, result_queue)
    )

    try:
        window.write_event_value("-LOG_MESSAGE-", "Starting Dither vectorization process...")
        start_time = time.time()
        
        process.start()

        while process.is_alive():
            if stop_event.is_set():
                print("Stop event received, terminating process.")
                process.terminate()
                process.join(timeout=1) # Give it a second to close
                if process.is_alive():
                    print("Process did not terminate gracefully, killing.")
                    process.kill()
                    process.join()
                return 
            
            time.sleep(0.1)

        end_time = time.time()
        window.write_event_value("-LOG_MESSAGE-", f"Dither process complete in {end_time - start_time:.2f} seconds.")

        # Check if the queue is empty, might happen if process is killed
        if result_queue.empty():
            print("Result queue is empty after process finished.")
            return

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
