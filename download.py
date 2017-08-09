from datetime import datetime
import sys
from update_image import UpdateImage


if __name__ == "__main__":
    if len(sys.argv) != 2:
        output_filename = "{:%Y_%m_%d-%H_%M_%S}.gif".format(datetime.now())
    else:
        output_filename = sys.argv[1]

    print("Downloading current sketch board screenshot")
    up = UpdateImage()
    up.update_image()
    up.save_buffer_to_file(output_filename)
    print("Save picture to %s" % output_filename)
