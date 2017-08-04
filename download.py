import requests
import time
import json
from PIL import Image

url = r"http://api.live.bilibili.com/activity/v1/SummerDraw/bitmap"

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

code_map = {v: k for k, v in color_map.items()}


def hex_to_rgb(rgb_hex):
    assert rgb_hex.startswith('#')
    assert len(rgb_hex) == 7
    r = int(rgb_hex[1:3], 16)
    g = int(rgb_hex[3:5], 16)
    b = int(rgb_hex[5:7], 16)
    return (r, g, b)


def convert_code_to_bytes(code_map, code_data):
    buf = bytearray(len(code_data) * 3)
    i = 0
    for code in code_data:
        rgb_hex = code_map[code]
        rgb = hex_to_rgb(rgb_hex)
        buf[i] = rgb[0]
        buf[i + 1] = rgb[1]
        buf[i + 2] = rgb[2]
        i += 3
    return buf


if __name__ == "__main__":
    r = requests.get(url)
    data = r.json()
    print("downloaded...")
    code_data = data["data"]["bitmap"]
    img_data = convert_code_to_bytes(code_map, code_data)
    img = Image.frombytes("RGB", (1280, 720), bytes(img_data))
    img.show()
    img.save('current_progress.gif', "GIF")
