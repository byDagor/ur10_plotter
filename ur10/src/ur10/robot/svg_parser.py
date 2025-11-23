from xml.dom import minidom
from svg.path import parse_path

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
    corner: str = "Top Left"
):
    """
    Parses an SVG file, scales it to fit the canvas, and converts path data into robot poses.

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
    :return: A tuple containing the list of robot poses, the scaled width (in meters),
             and the scaled height (in meters).
    """
    doc = minidom.parse(file_path)
    paths = doc.getElementsByTagName('path')
    
    if not paths:
        doc.unlink()
        return [], 0, 0

    # --- 1. First pass: Get all points and calculate bounding box of raw SVG ---
    all_points = []
    for path in paths:
        d = path.getAttribute('d')
        parsed = parse_path(d)
        for segment in parsed:
            # We are interested in the endpoints of each segment
            all_points.append((segment.end.real, segment.end.imag))
            
    if not all_points:
        doc.unlink()
        return [], 0, 0

    min_x_svg = min(p[0] for p in all_points)
    max_x_svg = max(p[0] for p in all_points)
    min_y_svg = min(p[1] for p in all_points)
    max_y_svg = max(p[1] for p in all_points)

    svg_width = max_x_svg - min_x_svg
    svg_height = max_y_svg - min_y_svg

    if svg_width == 0 or svg_height == 0:
        print("Warning: SVG width or height is zero. Cannot scale properly.")
        scale_factor = 1.0
    else:
        # --- 2. Calculate the scaling factor to fit canvas ---
        # Preserve aspect ratio by using the smaller of the two possible scales
        scale_x = canvas_width_mm / svg_width
        scale_y = canvas_height_mm / svg_height
        scale_factor = min(scale_x, scale_y)

    scaled_width_m = (svg_width * scale_factor) / 1000.0
    scaled_height_m = (svg_height * scale_factor) / 1000.0

    # --- 3. Second pass: Apply scaling and generate robot poses ---
    line_list = []
    for path in paths:
        d = path.getAttribute('d')
        parsed = parse_path(d)
        for segment in parsed:
            # Scale the point relative to the SVG's own origin
            scaled_x = (segment.end.real - min_x_svg) * scale_factor
            scaled_y = (segment.end.imag - min_y_svg) * scale_factor
            
            # Convert from mm to meters
            x_offset_m = scaled_x / 1000.0
            y_offset_m = scaled_y / 1000.0

            # --- 4. Apply corner logic to position the drawing ---
            # The robot's "start_x, start_y" is the origin point for the drawing on the canvas.
            if corner == "Top Left":
                x = start_x + x_offset_m
                y = start_y - y_offset_m
            elif corner == "Top Right":
                x = start_x - x_offset_m
                y = start_y - y_offset_m
            elif corner == "Bottom Left":
                x = start_x + x_offset_m
                y = start_y + y_offset_m
            elif corner == "Bottom Right":
                x = start_x - x_offset_m
                y = start_y + y_offset_m
            else: # Default to Top Left
                x = start_x + x_offset_m
                y = start_y - y_offset_m

            z = start_z if not dry_run else start_z + 0.02
            line_list.append((x, y, z, rx, ry, rz))

    doc.unlink()

    return line_list, scaled_width_m, scaled_height_m