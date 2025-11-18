from xml.dom import minidom
from svg.path import parse_path

def parse_svg(file_path: str, start_x: float, start_y: float, start_z: float, rx: float, ry: float, rz: float, scale: float, dry_run: bool = False, corner: str = "Top Left"):
    """
    Parses an SVG file and converts the path data into a list of robot poses.

    :param file_path: Path to the SVG file.
    :param start_x: Starting X coordinate for the robot.
    :param start_y: Starting Y coordinate for the robot.
    :param start_z: Starting Z coordinate for the robot.
    :param rx: Rotation around X for the robot.
    :param ry: Rotation around Y for the robot.
    :param rz: Rotation around Z for the robot.
    :param scale: Scaling factor for the SVG coordinates.
    :param dry_run: If True, the Z coordinate will not be modified for drawing.
    :param corner: The corner of the canvas to use as the origin.
    :return: A list of robot poses.
    """
    line_list = []
    doc = minidom.parse(file_path)
    
    for _, path in enumerate(doc.getElementsByTagName('path')):
        d = path.getAttribute('d')
        parsed = parse_path(d)
        for obj in parsed:
            x_offset = (round(obj.end.real, 3) / scale) / 1000
            y_offset = (round(obj.end.imag, 3) / scale) / 1000

            if corner == "Top Left":
                x = start_x - x_offset
                y = start_y - y_offset
            elif corner == "Top Right":
                x = start_x + x_offset
                y = start_y - y_offset
            elif corner == "Bottom Left":
                x = start_x - x_offset
                y = start_y + y_offset
            elif corner == "Bottom Right":
                x = start_x + x_offset
                y = start_y + y_offset
            else: # Default to Top Left
                x = start_x - x_offset
                y = start_y - y_offset

            z = start_z - 20 if not dry_run else start_z
            line_list.append((x, y, z, rx, ry, rz))
            
    doc.unlink()

    if not line_list:
        return [], 0, 0

    min_x = min(p[0] for p in line_list)
    max_x = max(p[0] for p in line_list)
    min_y = min(p[1] for p in line_list)
    max_y = max(p[1] for p in line_list)

    width = max_x - min_x
    height = max_y - min_y
    
    return line_list, width, height
