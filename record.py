#!/usr/bin/env python3

import asyncio
import os
from datetime import datetime
from async_update_image import AsyncUpdateImage

interval = 180
filename_template = "autosave/autosave_{:%Y_%m_%d-%H_%M_%S}.gif"


def print_log(filename):
    print("@%s record current image, save file %s" %
          (datetime.now(), filename))


async def wakeup():
    """ Keep script responsive to Ctrl+C
    """
    while True:
        await asyncio.sleep(1)


async def recording(up):
    while True:
        await up.async_update_image()
        filename = filename_template.format(datetime.now())
        up.save_buffer_to_file(filename)
        print_log(filename)
        await asyncio.sleep(interval)

if __name__ == "__main__":
    if not os.path.exists('autosave'):
        print("Create output folder autosave")
        os.makedirs("autosave")

    up = AsyncUpdateImage()
    print("Start @%s" % datetime.now())
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(asyncio.gather(recording(up), wakeup()))
    except KeyboardInterrupt:
        print("Ctrl+C pressed, existing")
    finally:
        up.close()
        loop.stop()
        loop.close()
