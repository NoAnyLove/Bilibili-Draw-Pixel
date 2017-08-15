#!/usr/bin/env python3

import asyncio
from datetime import datetime
import sys
from update_image import UpdateImage

filename_template = "autosave_{:%Y_%m_%d-%H_%M_%S}.gif"


async def downloading(up):
    await up.perform_update_image()
    filename = filename_template.format(datetime.now())
    up.save_buffer_to_file(filename)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        output_filename = filename_template.format(datetime.now())
    else:
        output_filename = sys.argv[1]

    print("Downloading current sketch board screenshot")
    up = UpdateImage()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(asyncio.gather(downloading(up)))
    except KeyboardInterrupt:
        print("Ctrl+C pressed, existing")
    finally:
        up.close()
        loop.stop()
        loop.close()
    print("Save picture to %s" % output_filename)
