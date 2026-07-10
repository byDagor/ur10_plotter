import math
from xml.dom import minidom
from svg.path import parse_path, Move, Close, Line
import re

_CURVE_SAMPLES = 16   # points per curved segment when flattening a <path>


def _points_from_path_d(d):
    """Flatten an SVG path 'd' string into continuous subpaths (lists of (x, y)).

    The svg.path library has no continuous_subpaths(), so we split on Move
    commands ourselves: a Line contributes its endpoint, curves/arcs are sampled,
    and Close appends the closing point. Segment endpoints are complex numbers
    whose (real, imag) are (x, y).
    """
    subpaths = []
    current = []

    def flush():
        if len(current) >= 2:
            subpaths.append(list(current))

    for seg in parse_path(d):
        if isinstance(seg, Move):
            flush()
            current.clear()
            current.append((seg.end.real, seg.end.imag))
        elif isinstance(seg, Close):
            if current:
                current.append((seg.end.real, seg.end.imag))
            flush()
            current.clear()
        elif isinstance(seg, Line):
            if not current:
                current.append((seg.start.real, seg.start.imag))
            current.append((seg.end.real, seg.end.imag))
        else:  # CubicBezier / QuadraticBezier / Arc -> sample along the curve
            if not current:
                current.append((seg.start.real, seg.start.imag))
            for i in range(1, _CURVE_SAMPLES + 1):
                p = seg.point(i / _CURVE_SAMPLES)
                current.append((p.real, p.imag))

    flush()
    return subpaths


def _get_points_from_element(element):
    """
    Extracts a list of lists of (x, y) points from different SVG element types.
    Each inner list represents a continuous subpath.
    """
    paths = []
    if element.tagName == 'path':
        paths.extend(_points_from_path_d(element.getAttribute('d')))

    elif element.tagName in ['polyline', 'polygon']:
        point_str = element.getAttribute('points')
        point_pairs = re.split(r'[ ,]+', point_str.strip())
        points = []
        for i in range(0, len(point_pairs), 2):
            try:
                x = float(point_pairs[i])
                y = float(point_pairs[i+1])
                points.append((x, y))
            except (ValueError, IndexError):
                continue # Skip malformed point pairs
        if element.tagName == 'polygon' and points:
             points.append(points[0]) # Close the polygon
        if points:
            paths.append(points)

    elif element.tagName == 'line':
        try:
            x1 = float(element.getAttribute('x1'))
            y1 = float(element.getAttribute('y1'))
            x2 = float(element.getAttribute('x2'))
            y2 = float(element.getAttribute('y2'))
            paths.append([(x1, y1), (x2, y2)])
        except ValueError:
            pass # Skip malformed lines
            
    return paths

def parse_svg(
    file_path: str,
    start_x: float,
    start_y: float,
    start_z: float,
    rx: float,
    ry: float,
    rz: float,
    canvas_width_mm: float,
    canvas_height_mm: float,
    dry_run: bool = False,
    corner: str = "Top Left",
    safe_z_offset: float = 0.01,
    rotation_angle: int = 0
):
    """
    Parses an SVG file, scales it to fit the canvas, and converts path data into robot poses.
    Handles <path>, <polyline>, <polygon>, and <line> elements.

    :param file_path: Path to the SVG file.
    :param start_x: Starting X coordinate for the robot (in meters).
    :param start_y: Starting Y coordinate for the robot (in meters).
    :param start_z: Starting Z coordinate for the robot (in meters).
    :param rx: Rotation around X for the robot.
    :param ry: Rotation around Y for the robot.
    :param rz: Rotation around Z for the robot.
    :param canvas_width_mm: The width of the target canvas in millimeters.
    :param canvas_height_mm: The height of the target canvas in millimeters.
    :param dry_run: If True, the Z coordinate will not be modified for drawing.
    :param corner: The corner of the canvas to use as the origin.
    :param safe_z_offset: The safe height offset for pen-up moves.
    :param rotation_angle: The global rotation to apply to the drawing.
    :return: A tuple containing a list of paths (each a list of poses), 
             the scaled width (in meters), and the scaled height (in meters).
    """
    try:
        doc = minidom.parse(file_path)
        svg_element = doc.getElementsByTagName('svg')[0]

        # --- 1. Get SVG dimensions from viewBox or width/height attributes ---
        viewbox_str = svg_element.getAttribute('viewBox')
        if viewbox_str:
            try:
                vb = [float(n) for n in re.split(r'[ ,]+', viewbox_str.strip())]
                min_x_svg, min_y_svg, svg_width, svg_height = vb[0], vb[1], vb[2], vb[3]
            except (ValueError, IndexError):
                print("Warning: Could not parse viewBox. Falling back to width/height.")
                svg_width = float(svg_element.getAttribute('width'))
                svg_height = float(svg_element.getAttribute('height'))
                min_x_svg, min_y_svg = 0, 0
        else:
            try:
                svg_width = float(svg_element.getAttribute('width'))
                svg_height = float(svg_element.getAttribute('height'))
                min_x_svg, min_y_svg = 0, 0
            except (ValueError, TypeError):
                 print("Warning: SVG has no viewBox or width/height attributes. Calculating bounds from elements.")
                 all_points = []
                 supported_tags = ['path', 'polyline', 'polygon', 'line']
                 elements = []
                 for tag in supported_tags:
                     elements.extend(doc.getElementsByTagName(tag))
                 for el in elements:
                     paths = _get_points_from_element(el)
                     for path in paths:
                        all_points.extend(path)
                 if not all_points:
                     return [], 0, 0
                 min_x_svg = min(p[0] for p in all_points)
                 max_x_svg = max(p[0] for p in all_points)
                 min_y_svg = min(p[1] for p in all_points)
                 max_y_svg = max(p[1] for p in all_points)
                 svg_width = max_x_svg - min_x_svg
                 svg_height = max_y_svg - min_y_svg
        
        # --- Handle cases where SVG has no size ---
        if svg_width == 0 or svg_height == 0:
            print("Warning: SVG width or height is zero. Using 1.0 as scale factor.")
            scale_factor = 1.0
        else:
            # --- 2. Calculate the scaling factor to fit canvas ---
            scale_x = canvas_width_mm / svg_width
            scale_y = canvas_height_mm / svg_height
            scale_factor = min(scale_x, scale_y)

        scaled_width_m = (svg_width * scale_factor) / 1000.0
        scaled_height_m = (svg_height * scale_factor) / 1000.0
        
        # --- 3. Second pass: Apply scaling and generate robot poses ---
        all_robot_paths = []
        supported_tags = ['path', 'polyline', 'polygon', 'line']
        elements = []
        for tag in supported_tags:
            elements.extend(doc.getElementsByTagName(tag))

        if not elements:
            return [], 0, 0

        angle_rad = math.radians(rotation_angle + 45)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
            
        for el in elements:
            subpaths = _get_points_from_element(el)
            for path_points in subpaths:
                robot_path = []
                for point in path_points:
                    # Scale the point relative to the SVG's own origin
                    scaled_x = (point[0] - min_x_svg) * scale_factor
                    scaled_y = (point[1] - min_y_svg) * scale_factor
                    
                    # Convert from mm to meters
                    x_offset_m = scaled_x / 1000.0
                    y_offset_m = scaled_y / 1000.0

                    # --- 4. Apply corner logic to position the drawing ---
                    # The robot's Y-axis is inverted relative to SVG's Y-axis.
                    # We define the drawing's top-left point in robot coordinates.
                    if corner == "Top Left":
                        origin_x, origin_y = start_x, start_y
                    elif corner == "Top Right":
                        origin_x, origin_y = start_x - scaled_width_m, start_y
                    elif corner == "Bottom Left":
                        origin_x, origin_y = start_x, start_y + scaled_height_m
                    elif corner == "Bottom Right":
                        origin_x, origin_y = start_x - scaled_width_m, start_y + scaled_height_m
                    elif corner == "Center":
                        origin_x, origin_y = start_x - scaled_width_m / 2, start_y + scaled_height_m / 2
                    else: # Default to Top Left
                        origin_x, origin_y = start_x, start_y

                    x = origin_x + x_offset_m
                    y = origin_y - y_offset_m

                    # --- 5. Apply rotation around the home point ---
                    x_rotated = start_x + (x - start_x) * cos_a - (y - start_y) * sin_a
                    y_rotated = start_y + (x - start_x) * sin_a + (y - start_y) * cos_a
                        
                    z = start_z if not dry_run else start_z + safe_z_offset # Lift pen for dry run
                    robot_path.append((x_rotated, y_rotated, z, rx, ry, rz))
                if robot_path:
                    all_robot_paths.append(robot_path)

        return all_robot_paths, scaled_width_m, scaled_height_m
        
    except Exception as e:
        print(f"Error parsing SVG file '{file_path}': {e}")
        import traceback
        traceback.print_exc()
        return [], 0, 0
    finally:
        if 'doc' in locals():
            doc.unlink()