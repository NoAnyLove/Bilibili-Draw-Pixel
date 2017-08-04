import requests
import threading
import time
import os
from datetime import datetime
from PIL import Image
from util import code_map, hex_to_rgb


__all__ = ["UpdateImage"]

url = r"http://api.live.bilibili.com/activity/v1/SummerDraw/bitmap"


class UpdateImage(object):
    def __init__(self, autosave=False, lazy_threshold=60):
        self.width = 1280
        self.height = 720
        self.image_buffer = bytearray(self.width * self.height * 3)
        self.sync_lock = threading.RLock()
        self.interval = 180
        self.filename_template = "autosave/autosave_{:%Y_%m_%d-%H_%M_%S}.gif"
        self.exist_dir = False
        self.last_update = None
        self.autosave = autosave
        self.lazy_threshold = lazy_threshold
        self.timeout = 15

    def get_auto_save_filename(self):
        return self.filename_template.format(datetime.now())

    def update_image(self, auto_save=False):
        print("Downloading %s" % url)
        try:
            r = requests.get(url, timeout=self.timeout)
        except requests.ConnectionError:
            print("Failed to connect to Bilibili.com")
            return
        except requests.ConnectTimeout:
            print("Connection timeout, failed to update image")
            return
        try:
            data = r.json()
            code_data = data["data"]["bitmap"]
        except Exception as e:
            print("Failed to update image with error: %s" % e)
            return

        print("Enter critical section: update image date")
        # thread synchronization
        with self.sync_lock:
            convert_code_to_bytes(code_map, code_data, self.image_buffer)
            if auto_save or self.autosave:
                if not self.exist_dir and not os.path.exists('autosave'):
                    print("Create output folder autosave")
                    os.makedirs("autosave")
                    self.exist_dir = True

                filename = self.get_auto_save_filename()
                self.save_buffer_to_file(filename)
                print('Auto save file to {}'.format(filename))

            self.last_update = time.time()

        print("Left critical section: finish update")

    def lazy_update_image(self, auto_save=False):
        ret = -1
        with self.sync_lock:
            if self.last_update is None:
                self.update_image(auto_save)
            elif time.time() > self.last_update + self.lazy_threshold:
                self.update_image(auto_save)
            else:
                ret = self.last_update
        return ret

    def get_image_pixel(self, x, y):
        index = y * self.width + x
        with self.sync_lock:
            r = self.image_buffer[index * 3]
            g = self.image_buffer[index * 3 + 1]
            b = self.image_buffer[index * 3 + 2]
        return (r, g, b)

    def save_buffer_to_file(self, filename):
        img = Image.frombytes("RGB", (1280, 720), bytes(self.image_buffer))
        img.save(filename, "GIF")

    def thread_main(self):
        while True:
            self.update_image()
            time.sleep(self.interval)

    def start_update_thread(self):
        thread = threading.Thread(target=self.thread_main)
        thread.daemon = True
        thread.start()
        self.thread = thread
        return thread


def convert_code_to_bytes(code_map, code_data, buf):
    i = 0
    for code in code_data:
        rgb_hex = code_map[code]
        rgb = hex_to_rgb(rgb_hex)
        buf[i] = rgb[0]
        buf[i + 1] = rgb[1]
        buf[i + 2] = rgb[2]
        i += 3
    return buf