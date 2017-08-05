import time
import subprocess
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color

color_map = {"#000000": "0",
             "#2e8faf": "I",
             "#3be5db": "6",
             "#7d9591": "4",
             "#44c95f": "C",
             "#71bed6": "5",
             "#97fddc": "G",
             "#004670": "A",
             "#7754ff": "D",
             "#057197": "B",
             "#b83f27": "8",
             "#f8cb8c": "H",
             "#faac8e": "9",
             "#fcde6b": "2",
             "#fed3c7": "7",
             "#ff0000": "E",
             "#ff9800": "F",
             "#ffffff": "1",
             "#fff6d1": "3"}

missing_color_table = {
    "#f0fdf3": "#ffffff",
    '#137b9f': '#057197',
    '#5aced8': '#71bed6',
    '#42d5d5': '#3be5db',
    '#60b2cc': '#71bed6',
    '#10577e': '#004670',
}

code_map = {v: k for k, v in color_map.items()}


def missing_color(rgb_hex):
    rgb_hex = rgb_hex.lower()
    try:
        rgb_hex = missing_color_table[rgb_hex]
    except KeyError:
        # TODO: currently just set it to black, need improvement
        raise ValueError("Cannot process missing color %s" % rgb_hex)
    return rgb_hex


def rgb_to_hex(r, g, b):
    return "#%02x%02x%02x" % (r, g, b)


def hex_to_rgb(rgb_hex):
    assert rgb_hex.startswith('#')
    assert len(rgb_hex) == 7
    r = int(rgb_hex[1:3], 16)
    g = int(rgb_hex[3:5], 16)
    b = int(rgb_hex[5:7], 16)
    return (r, g, b)


def rgb_to_lab(r, g, b):
    rgb_color = sRGBColor(r, g, b)
    lab_color = convert_color(rgb_color, LabColor)
    return lab_color.get_value_tuple()


lab_map = {rgb_to_lab(*hex_to_rgb(rgb_hex)): rgb_hex
           for rgb_hex in color_map.keys()}


def dist(color1, color2):
    return sum((a - b)**2 for a, b in zip(color1, color2))


def avialalbe_in_pallete(rgb_hex):
    return rgb_hex in color_map


def rgb_hex_to_color_code(rgb_hex):
    if rgb_hex not in color_map:
        rgb_hex = missing_color(rgb_hex)
    return color_map[rgb_hex]


def find_nearest_color(r, g, b):
    """return the RGB hex of the nearest color in available palette
    """
    lab_color = rgb_to_lab(r, g, b)
    nearest_lab = min(lab_map.keys(), key=lambda x: dist(lab_color, x))
    return lab_map[nearest_lab]


def process_task_missing_color(tasks):
    """in-place tasks processing, convert missing colors to available colors
    """
    for i in xrange(len(tasks)):
        x, y, rgb_hex = tasks[i]
        if rgb_hex not in color_map:
            rgb_hex = missing_color(rgb_hex)
            tasks[i] = (x, y, rgb_hex)


def draw_pixel(cmd_template, x, y, rgb_hex):
    color_code = rgb_hex_to_color_code(rgb_hex)
    try:
        start_time = time.time()
        output = subprocess.check_output(cmd_template.format(
            **{'x': x, 'y': y, 'color': color_code}), shell=True)
    except Exception:
        output = ''
    return output, time.time() - start_time
