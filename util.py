import time
import re
import collections
import json
from datetime import datetime
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
import aiohttp


def rgb_to_hex(r, g, b):
    return "#%02x%02x%02x" % (r, g, b)


def hex_to_rgb(rgb_hex):
    assert rgb_hex.startswith('#')
    assert len(rgb_hex) == 7
    r = int(rgb_hex[1:3], 16)
    g = int(rgb_hex[3:5], 16)
    b = int(rgb_hex[5:7], 16)
    return (r, g, b)


# '#2196f3' -> 'G'
COLOR_CODE_TABLE = {
    '#2196f3': 'G',
    '#9c27b0': 'B',
    '#ff5722': 'T',
    '#ffeb3b': 'Q',
    '#fff6d1': 'O',
    '#fed3c7': '4',
    '#167300': 'K',
    '#89e642': 'M',
    '#ff9800': 'S',
    '#97fddc': 'J',
    '#673ab7': 'C',
    '#004670': 'E',
    '#f8cb8c': 'P',
    '#e91e63': '9',
    '#37a93c': 'L',
    '#b83f27': 'U',
    '#795548': 'V',
    '#ffc4ce': '5',
    '#057197': 'F',
    '#ffffff': '1',
    '#000000': '0',
    '#00bcd4': 'H',
    '#ffc107': 'R',
    '#3f51b5': 'D',
    '#aaaaaa': '2',
    '#faac8e': '6',
    '#3be5db': 'I',
    '#d7ff07': 'N',
    '#555555': '3',
    '#ff8b83': '7',
    '#e2669e': 'A',
    '#f44336': '8'
}

# 'G' -> '#2196f3'
CODE_COLOR_TABLE = {v: k for k, v in COLOR_CODE_TABLE.items()}

# (255, 255, 255) -> '1'
RGB_CODE_TABLE = {hex_to_rgb(k): v for k, v in COLOR_CODE_TABLE.items()}

# '1' -> (255, 255, 255)
CODE_RGB_TABLE = {v: k for k, v in RGB_CODE_TABLE.items()}

missing_color_table = {
    "#f0fdf3": "#ffffff",
    '#137b9f': '#057197',
    '#5aced8': '#71bed6',
    '#42d5d5': '#3be5db',
    '#60b2cc': '#71bed6',
    '#10577e': '#004670',
}


def missing_color(rgb_hex):
    rgb_hex = rgb_hex.lower()
    try:
        rgb_hex = missing_color_table[rgb_hex]
    except KeyError:
        # TODO: currently just set it to black, need improvement
        raise ValueError("Cannot process missing color %s" % rgb_hex)
    return rgb_hex


def rgb_to_lab(r, g, b):
    rgb_color = sRGBColor(r, g, b)
    lab_color = convert_color(rgb_color, LabColor)
    return lab_color.get_value_tuple()


lab_map = {rgb_to_lab(*hex_to_rgb(rgb_hex)): rgb_hex
           for rgb_hex in COLOR_CODE_TABLE.keys()}


def dist(color1, color2):
    return sum((a - b)**2 for a, b in zip(color1, color2))


def avialalbe_in_pallete(rgb_hex):
    return rgb_hex in COLOR_CODE_TABLE


def rgb_hex_to_color_code(rgb_hex):
    if rgb_hex not in COLOR_CODE_TABLE:
        rgb_hex = missing_color(rgb_hex)
    return COLOR_CODE_TABLE[rgb_hex]


def find_nearest_color(r, g, b):
    """return the RGB hex of the nearest color in available palette
    """
    lab_color = rgb_to_lab(r, g, b)
    nearest_lab = min(lab_map.keys(), key=lambda x: dist(lab_color, x))
    return lab_map[nearest_lab]


def process_tasks(tasks):
    """in-place tasks processing, convert missing colors to available colors
    """
    # TODO: it might be better to use collections.defaultdict(str)
    tasks_dict = collections.OrderedDict()
    for i in range(len(tasks)):
        x, y, rgb_hex = tasks[i]
        if rgb_hex not in COLOR_CODE_TABLE:
            # TODO: improve the way to process missing color
            rgb_hex = missing_color(rgb_hex)
        color_code = COLOR_CODE_TABLE[rgb_hex]
        tasks_dict[(x, y)] = color_code
    return tasks_dict


fake_request_header = {
    'user-agent': r'Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit'
    '/537.36 (KHTML, like Gecko) Chrome/60.0.3112.78 Safari/537.36',
    'Origin': r'http://live.bilibili.com',
    'Referer': r'http://live.bilibili.com/pages/1702/pixel-drawing'
}

post_url = r'http://api.live.bilibili.com/activity/v1/SummerDraw/draw'
cookie_pattern = r"-H 'Cookie: ([^']+)'"


def extract_cookies(cmd_template):
    cookies = dict()
    match = re.search(cookie_pattern, cmd_template)
    if match is None:
        return None
    cookies_str = match.group(1)
    for field in cookies_str.split('; '):
        key, value = field.split('=')
        cookies[key] = value
    return cookies


async def async_draw_pixel_with_requests(session, x, y, color_code):
    payload = dict(x_min=x, y_min=y, x_max=x, y_max=y, color=color_code)
    output = ''
    try:
        start_time = time.time()
        async with session.post(post_url, data=payload,
                                headers=fake_request_header, timeout=60) as r:
            output = await r.text()

    except aiohttp.ClientConnectionError:
        print("draw_pixel: Failed to connect to Bilibili.com")
    except aiohttp.ServerTimeoutError:
        print("draw_pixel: Connection timeout")
    except Exception as e:
        print("draw_pixel: error occurs %s" % e)

    # sometimes failed to get json
    try:
        status = None
        status_code = None

        status = json.loads(output)
        status_code = status['code']
        wait_time = status['data']['time']
    except Exception:

        # sleep 30 seconds if failed, avoid busy loop
        wait_time = 30

    return status_code, wait_time, time.time() - start_time


def process_status_101(user_counters, worker_id, user_id, cost_time, workers):
    # use a list container to hold an integer
    user_counters[user_id] += 1
    times = user_counters[user_id]
    print("@%s, <worker-%s> has status -101 for %d times, cost %.2fs"
          % (datetime.now(), worker_id,
              times, cost_time))
    if times >= 10:
        print("@%s, <worker-%s> exiting because of invalid cookie, associated"
              " uid: %s" %
              (datetime.now(), worker_id, user_id))
        workers[worker_id].cancel()


def get_task_priority(priority_dict, x, y, default_priority=0):
    return priority_dict.get((x, y), default_priority)
