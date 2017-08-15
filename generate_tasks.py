import json
import argparse
import sys
from PIL import Image
from util import rgb_to_hex


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--ref', dest='reference_filename',
                        default="reference.gif")
    parser.add_argument('-o', dest='output_filename',
                        required=True)
    parser.add_argument('--rect', nargs=4, type=int,
                        metavar=('left', 'top', 'right', 'bottom'))
    parser.add_argument('--pattern', dest='pattern_filename')
    parser.add_argument('--topleft', nargs=2, type=int,
                        metavar=('left', 'top'))

    args = parser.parse_args()

    img = Image.open(args.reference_filename)
    img_rgb = img.convert('RGB')
    m, n = img.size

    tasks = []
    if args.pattern_filename is not None:
        assert args.topleft is not None, "--topleft parameter is missing"
        img_pattern = Image.open(args.pattern_filename)
        if img_pattern.mode != 'RGBA':
            img_pattern = img_pattern.convert("RGBA")
        # img_rgb.paste(img_pattern, args.topleft, img_pattern)
        width, height = img_pattern.size
        x_boundary, y_boundary = img_rgb.size
        x_base, y_base = args.topleft
        for x in range(width):
            for y in range(height):
                assert x_base + x < x_boundary, \
                    "pattern image (%d,%d) is out of scope" % (x, y)
                assert y_base + y < y_boundary, \
                    "pattern image (%d,%d) is out of scope" % (x, y)
                r, g, b, a = img_pattern.getpixel((x, y))
                # skip transparent pixels
                if a == 0:
                    continue
                tasks.append((x + x_base, y + y_base, rgb_to_hex(r, g, b)))

    if args.rect is not None:
        start_x, start_y, end_x, end_y = args.rect
        for y in range(start_y, end_y + 1):
            for x in range(start_x, end_x + 1):
                r, g, b = img_rgb.getpixel((x, y))
                # print(x, y, rgb_to_hex(r, g, b))
                tasks.append((x, y, rgb_to_hex(r, g, b)))

    if not tasks:
        print("No task was generated")
        sys.exit()

    try:
        with open(args.output_filename, "w") as fp:
            json.dump(tasks, fp)
        print("Write %d tasks to %s" % (len(tasks), args.output_filename))
    except IOError as e:
        print("Failed to write tasks to %s, with error: " %
              (args.output_filename, e))
