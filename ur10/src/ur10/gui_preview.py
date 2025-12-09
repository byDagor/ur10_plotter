import FreeSimpleGUI as sg
import vpype
import io
from PIL import Image, ImageOps
import xml.etree.ElementTree as ET

# --- MATPLOTLIB IMPORTS ---
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.patches import Polygon, Circle
from matplotlib.collections import PatchCollection
# --------------------------------

def preview_dots_from_svg(window: sg.Window, file_path: str):
    image_key = "-SVG_PREVIEW_IMAGE-"
    # Get the current size of the element
    try:
        max_size = window[image_key].get_size()
    except Exception:
        # Fallback if window or element isn't available yet
        max_size = (600, 600)

    dpi = 100
    fig = Figure(figsize=(max_size[0] / dpi, max_size[1] / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    ax.set_facecolor('white')
    fig.set_facecolor('white')

    try:
        points = []
        namespaces = {'svg': 'http://www.w3.org/2000/svg'}
        tree = ET.parse(file_path)
        root = tree.getroot()
        for line in root.findall('.//svg:line', namespaces):
            try:
                x1, y1 = float(line.get('x1')), float(line.get('y1'))
                points.append((x1, y1))
            except (ValueError, TypeError):
                continue
        if points:
            min_x, max_x = min(p[0] for p in points), max(p[0] for p in points)
            min_y, max_y = min(p[1] for p in points), max(p[1] for p in points)
            ax.set_xlim(min_x, max_x)
            ax.set_ylim(min_y, max_y)
            ax.invert_yaxis()
            ax.set_aspect('equal', adjustable='box')
            patches = [Circle(p, radius=0.1) for p in points]
            p_collection = PatchCollection(patches, facecolor='black', edgecolor='black')
            ax.add_collection(p_collection)
    except Exception as e:
        print(f"Error manually parsing SVG: {e}")

    try:
        canvas = FigureCanvas(fig)
        canvas.draw()
        buf = canvas.buffer_rgba()
        img = Image.frombytes("RGBA", canvas.get_width_height(), buf)
        png_buffer = io.BytesIO()
        img.save(png_buffer, format="PNG")
        window[image_key].update(data=png_buffer.getvalue())
    except Exception as e:
        print(f"Error saving canvas to PNG for {image_key}: {e}")
        img = Image.new('RGB', max_size, color='white')
        bio = io.BytesIO()
        img.save(bio, format='PNG')
        window[image_key].update(data=bio.getvalue())

def _render_document_to_image_element(window: sg.Window, document: vpype.Document, image_key: str, is_cmyk: bool):
    """
    Renders a vpype.Document to a dynamically sized sg.Image element.
    """
    try:
        # Get the current size of the element at runtime
        max_size = window[image_key].get_size()
        if max_size == (1, 1) or max_size == (0, 0): # Element might not be drawn yet
             max_size = (600, 600) # Fallback to a default
    except Exception:
        max_size = (600, 600)

    dpi = 100
    
    # 1. Render on a square canvas in memory matching the element's aspect ratio
    fig = Figure(figsize=(max_size[0] / dpi, max_size[1] / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    ax.set_facecolor('white')
    fig.set_facecolor('white')

    if document and not document.is_empty():
        try:
            bounds = document.bounds()
            if bounds:
                min_x, min_y, max_x, max_y = bounds
                ax.set_xlim(min_x, max_x)
                ax.set_ylim(min_y, max_y)
                ax.invert_yaxis()
                ax.set_aspect('equal', adjustable='box')
            
            color_map = {1: 'cyan', 2: 'magenta', 3: 'yellow', 4: 'black'}
            for layer_id, line_collection in document.layers.items():
                color = color_map.get(layer_id, 'black') if is_cmyk else 'black'
                
                if "DITHER" in image_key:
                    patches = [Polygon([(p.real, p.imag) for p in line], closed=True) for line in line_collection if len(line) > 2]
                    p = PatchCollection(patches, facecolor=color, edgecolor=color, linewidth=0.1)
                    ax.add_collection(p)
                else:
                    for line in line_collection:
                        x_data = [p.real for p in line]
                        y_data = [p.imag for p in line]
                        ax.plot(x_data, y_data, color=color, linewidth=0.5)
        except Exception as e:
            print(f"Error during Matplotlib rendering for {image_key}: {e}")

    try:
        canvas = FigureCanvas(fig)
        canvas.draw()
        buf = canvas.buffer_rgba()
        img = Image.frombytes("RGBA", canvas.get_width_height(), buf)

        bbox = ImageOps.invert(img.convert('RGB')).getbbox()
        if bbox:
            img = img.crop(bbox)

        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        final_img = Image.new("RGBA", max_size, (255, 255, 255, 0)) # Use transparent background
        paste_x = (max_size[0] - img.width) // 2
        paste_y = (max_size[1] - img.height) // 2
        final_img.paste(img, (paste_x, paste_y), img)

        png_buffer = io.BytesIO()
        final_img.save(png_buffer, format="PNG")
        window[image_key].update(data=png_buffer.getvalue())

    except Exception as e:
        print(f"Error during PIL processing for {image_key}: {e}")
        img = Image.new('RGB', max_size, color='white')
        bio = io.BytesIO()
        img.save(bio, format='PNG')
        window[image_key].update(data=bio.getvalue())

def update_preview(window: sg.Window, document: vpype.Document, is_cmyk: bool, image_key: str):
    _render_document_to_image_element(window, document, is_cmyk, image_key)

def update_svg_preview(window: sg.Window, document: vpype.Document):
    _render_document_to_image_element(window, document, "-SVG_PREVIEW_IMAGE-", False)

def update_flow_preview(window: sg.Window, document: vpype.Document, is_cmyk: bool):
    _render_document_to_image_element(window, document, "-PREVIEW_IMAGE_FLOW-", is_cmyk)

def update_hatched_preview(window: sg.Window, document: vpype.Document, is_cmyk: bool):
    _render_document_to_image_element(window, document, "-PREVIEW_IMAGE_HATCHED-", is_cmyk)

def update_dither_preview(window: sg.Window, document: vpype.Document):
    _render_document_to_image_element(window, document, "-PREVIEW_IMAGE_DITHER-", False)
