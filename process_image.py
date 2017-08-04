import sys
import time

from PIL import Image
from util import find_nearest_color, hex_to_rgb, color_map


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: %s input_filename output_filename" % sys.argv[0])
        sys.exit()
    in_filename = sys.argv[1]
    out_filename = sys.argv[2]
    print("Reading from %s" % in_filename)
    image = Image.open(in_filename)
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    width, height = image.size
    print("Start converting")
    start_time = time.time()
    cache = {}
    rgb_table = {hex_to_rgb(rgb_hex) for rgb_hex in color_map.keys()}

    def process_rgba(r, g, b, a):
        rgb = (r, g, b)
        if rgb in rgb_table:
            rr, gg, bb = r, g, b
        elif rgb in cache:
            rr, gg, bb = cache[rgb]
        else:
            nearest_rgb_hex = find_nearest_color(r, g, b)
            rr, gg, bb = hex_to_rgb(nearest_rgb_hex)
            cache[rgb] = rr, gg, bb
        return (rr, gg, bb, a)

    rgba_data = [process_rgba(*rgba) for rgba in image.getdata()]
    image.putdata(rgba_data)

    print("Cost %.2f seconds, processed %d colors" %
          (time.time() - start_time, len(cache)))
    print("Writing to %s" % out_filename)
    image.save(out_filename)
