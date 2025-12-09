import FreeSimpleGUI as sg
import vpype as vp
from vpype_cli import execute
import numpy as np
import threading
import time
import traceback
from PIL import Image, ImageEnhance, ImageStat, ImageOps, ImageChops
import random
import os
import multiprocessing
import tempfile

def image_to_cmyk_separation(img, contrast_factor=1.0):
    """
    Splits image into CMYK using 100% GCR (Gray Component Replacement).
    This maximizes the usage of Black (K) and removes that density from C, M, and Y.
    """
    # 1. Prepare RGB image (Handle transparency)
    img = img.convert('RGBA')
    background = Image.new('RGBA', img.size, (255, 255, 255))
    rgb_img = Image.alpha_composite(background, img).convert('RGB')
    
    # Apply contrast
    enhancer = ImageEnhance.Contrast(rgb_img)
    rgb_img = enhancer.enhance(contrast_factor)
    
    r, g, b = rgb_img.split()
    
    c_ink = ImageOps.invert(r)
    m_ink = ImageOps.invert(g)
    y_ink = ImageOps.invert(b)
    
    k_ink = ImageChops.darker(c_ink, m_ink)
    k_ink = ImageChops.darker(k_ink, y_ink)
    
    c_ink = ImageChops.subtract(c_ink, k_ink)
    m_ink = ImageChops.subtract(m_ink, k_ink)
    y_ink = ImageChops.subtract(y_ink, k_ink)
    
    c = ImageOps.invert(c_ink)
    m = ImageOps.invert(m_ink)
    y = ImageOps.invert(y_ink)
    k = ImageOps.invert(k_ink)
    
    return {'c': c, 'm': m, 'y': y, 'k': k}


class DitherVectorizer:
    def __init__(self, image_path: str, dither_method: str, contrast_factor: float = 1.0, density: float = 1.0, h_dots: int = 150, dot_radius_mm: float = 0.175, cmyk_dither: bool = False, cmyk_channels: dict = {}, pixel_offset: int = 0):
        self.image_path = image_path
        self.dither_method = dither_method
        self.contrast_factor = contrast_factor
        self.density = density
        self.h_dots = h_dots
        self.dot_radius_mm = dot_radius_mm
        self.cmyk_dither = cmyk_dither
        self.cmyk_channels = cmyk_channels
        self.pixel_offset = pixel_offset

        self.points = []
        self.c_points, self.m_points, self.y_points, self.k_points = [], [], [], []

    def run(self):
        # --- Image Preparation ---
        base_img = Image.open(self.image_path)
        original_width, original_height = base_img.size
        
        aspect_ratio = original_height / original_width
        new_width = self.h_dots
        new_height = round(new_width * aspect_ratio)
        img = base_img.resize((new_width, new_height))

        # --- Dithering ---
        if self.cmyk_dither:
            self.cmyk_fs_dither(img, new_width, new_height)
        else:
            img = img.convert("L") # Convert to grayscale for non-cmyk
            if self.dither_method == "Floyd-Steinberg":
                self.fs_dither(img, new_width, new_height)
            elif self.dither_method == "Ordered (Halftone)":
                self.ordered_dither(img, new_width, new_height)
            elif self.dither_method == "Stochastic (Random)":
                self.random_dither(img, new_width, new_height)
        
        # --- SVG Generation ---
        return self.get_document()

    def cmyk_fs_dither(self, img, new_width, new_height):
        cmyk_images = image_to_cmyk_separation(img, self.contrast_factor)
        
        channels_to_process = []
        if self.cmyk_channels.get('c'): channels_to_process.append(('c', cmyk_images['c'], self.c_points))
        if self.cmyk_channels.get('m'): channels_to_process.append(('m', cmyk_images['m'], self.m_points))
        if self.cmyk_channels.get('y'): channels_to_process.append(('y', cmyk_images['y'], self.y_points))
        if self.cmyk_channels.get('k'): channels_to_process.append(('k', cmyk_images['k'], self.k_points))

        for channel_code, channel_img, point_list in channels_to_process:
            flat_data = list(channel_img.getdata())
            pixels = [flat_data[i * new_width:(i + 1) * new_width] for i in range(new_height)]

            for y in range(new_height):
                for x in range(new_width):
                    old_pixel = pixels[y][x]
                    new_pixel = 255 if old_pixel > 127 else 0
                    pixels[y][x] = new_pixel
                    
                    error = old_pixel - new_pixel

                    if x + 1 < new_width: pixels[y][x + 1] += error * 7 / 16
                    if x - 1 >= 0 and y + 1 < new_height: pixels[y + 1][x - 1] += error * 3 / 16
                    if y + 1 < new_height: pixels[y + 1][x] += error * 5 / 16
                    if x + 1 < new_width and y + 1 < new_height: pixels[y + 1][x + 1] += error * 1 / 16
            
            norm_dim = max(new_width, new_height)
            
            offset_x, offset_y = 0, 0
            if channel_code == 'm': offset_x = self.pixel_offset
            if channel_code == 'y': offset_y = self.pixel_offset
            if channel_code == 'k':
                offset_x = self.pixel_offset
                offset_y = self.pixel_offset

            for y in range(new_height):
                for x in range(new_width):
                    if pixels[y][x] == 0:
                        px = ((x + offset_x) / norm_dim) * 100 + random.uniform(-0.05, 0.05)
                        py = ((y + offset_y) / norm_dim) * 100 + random.uniform(-0.05, 0.05)
                        point_list.append((px, py))

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
        doc = vp.Document()

        if self.cmyk_dither:
            point_map = {1: self.c_points, 2: self.m_points, 3: self.y_points, 4: self.k_points}
            for layer_id, points in point_map.items():
                if not points:
                    continue
                all_circle_lines = []
                for x, y in points:
                    angles = np.linspace(0, 2 * np.pi, num_segments, endpoint=False)
                    circle_points = [complex(x + self.dot_radius_mm * np.cos(a), y + self.dot_radius_mm * np.sin(a)) for a in angles]
                    circle_points.append(circle_points[0])
                    all_circle_lines.append(np.array(circle_points))
                lc = vp.LineCollection(all_circle_lines)
                doc.add(lc, layer_id=layer_id)
            return doc

        if not self.points:
            return vp.Document()

        all_circle_lines = []
        for x, y in self.points:
            angles = np.linspace(0, 2 * np.pi, num_segments, endpoint=False)
            circle_points = [complex(x + self.dot_radius_mm * np.cos(a), y + self.dot_radius_mm * np.sin(a)) for a in angles]
            circle_points.append(circle_points[0])
            all_circle_lines.append(np.array(circle_points))

        lc = vp.LineCollection(all_circle_lines)
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
            dot_radius_mm=params.get("dot_radius_mm", 0.175),
            cmyk_dither=params.get("cmyk_dither", False),
            cmyk_channels=params.get("cmyk_channels", {}),
            pixel_offset=params.get("pixel_offset", 0)
        )
        document = vectorizer.run()

        if document and not document.is_empty():
            # Use a temporary file to pass the document back
            fd, temp_path = tempfile.mkstemp(suffix=".svg")
            os.close(fd)
            with open(temp_path, "w", encoding="utf-8") as f:
                vp.write_svg(f, document)
            result_queue.put((True, temp_path, params.get("cmyk_dither", False)))
        else:
            result_queue.put((False, "Dithering resulted in an empty document.", False))

    except Exception as e:
        traceback.print_exc()
        result_queue.put((False, str(e), False))

def run_dither_thread(window: sg.Window, params: dict, stop_event: "threading.Event"):
    """
    This function runs in a thread and manages a separate process for the
    actual dithering work. This allows the work to be terminated and avoids GIL issues.
    """
    # Log the parameters being used
    is_cmyk = params.get("cmyk_dither", False)
    param_str = (
        f"Method: {'CMYK Floyd-Steinberg' if is_cmyk else params.get('method')}, "
        f"H-Dots: {params.get('h_dots')}, "
        f"Pen Diameter: {params.get('pen_diameter_mm')}mm, "
    )
    if is_cmyk:
        channels = [ch.upper() for ch, active in params.get("cmyk_channels", {}).items() if active]
        param_str += f"Channels: {', '.join(channels)}, Offset: {params.get('pixel_offset')}"
    elif params.get('method') == "Floyd-Steinberg":
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

        success, result_path_or_msg, is_cmyk_result = result_queue.get()

        if success:
            temp_path = result_path_or_msg
            window.write_event_value("-LOG_MESSAGE-", "Loading document from temp file...")
            document = execute(f'read "{temp_path}"')
            try:
                os.remove(temp_path)
            except OSError as e:
                print(f"Error removing temp file {temp_path}: {e}")
            
            window.write_event_value("-THREAD_DONE-", (document, "Dither vectorization complete.", is_cmyk_result))
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
