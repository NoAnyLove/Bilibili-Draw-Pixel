import collections
import requests
import struct
import threading
import time
import os
import json
from datetime import datetime
from PIL import Image
import websocket
from util import code_map, hex_to_rgb


__all__ = ["UpdateImage"]

url = r"http://api.live.bilibili.com/activity/v1/SummerDraw/bitmap"

token = bytearray([0x00, 0x00, 0x00, 0x27, 0x00, 0x10, 0x00, 0x01, 0x00, 0x00,
                   0x00, 0x07, 0x00, 0x00, 0x00, 0x01, 0x7B, 0x22, 0x75, 0x69,
                   0x64, 0x22, 0x3A, 0x30, 0x2C, 0x22, 0x72, 0x6F, 0x6F, 0x6D,
                   0x69, 0x64, 0x22, 0x3A, 0x35, 0x34, 0x34, 0x36, 0x7D])

heart_beat = bytearray([0x00, 0x00, 0x00, 0x10, 0x00, 0x10, 0x00, 0x01, 0x00,
                        0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x01])

"""
Protocol:

4 - JSON message end offset
2 - JSON message start offset
2 - unknown1
4 - opcode
    3 - something for online
    5 - msg
4 - unknown2, padding?
"""
message_header_struct = struct.Struct("!IHHI")
MessageHeader = collections.namedtuple("MessageHeader",
                                       [
                                           "end_offset",
                                           "start_offset",
                                           "unknown1",
                                           "opcode",
                                       ])


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
        self.timeout = 30
        self.ws = websocket.WebSocketApp(
            r"ws://broadcastlv.chat.bilibili.com:2244/sub",
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close)
        self.ws.on_open = self.on_open
        self.ws_loop_thread = None
        self.heart_beat_thread = None
        self.enable_reconnect = True

    def get_auto_save_filename(self):
        return self.filename_template.format(datetime.now())

    def update_image(self, auto_save=False):
        """ Avoid invoking this method in different threads
        """
        print("Downloading %s" % url)
        try:
            r = requests.get(url, timeout=self.timeout)
        except requests.ConnectionError:
            print("Failed to connect to Bilibili.com")
            return
        except requests.ConnectTimeout:
            print("Connection timeout, failed to update image")
            return
        except Exception as e:
            print("Error occurs: %s" % e)
            return
        try:
            data = r.json()
            code_data = data["data"]["bitmap"]
        except Exception as e:
            print("Failed to update image with error: %s" % e)
            return

        if not isinstance(code_data, basestring):
            print("Incorrect code data: %s" % code_data)
            return
        if len(code_data) != 1280 * 720:
            print("Code data length mismatch: %d" % len(code_data))

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
        start_time = time.time()
        # enter critical section
        with self.sync_lock:
            if self.last_update is None:
                self.update_image(auto_save)
            elif time.time() > self.last_update + self.lazy_threshold:
                # Since we use RLock, the whole process of calling
                # up.update_image from this place is still inside the critical
                # section. It is not possible that two threads calling
                # up.update_image from lazy_update_image simultaneously
                self.update_image(auto_save)
            else:
                ret = self.last_update
        end_time = time.time()
        if ret == -1:
            print("update image in %.2fs" %
                  (end_time - start_time))
        else:
            print("lazily updated %.2fs before" %
                  (end_time - ret))
        return ret

    def get_image_pixel(self, x, y):
        index = y * self.width + x
        r = self.image_buffer[index * 3]
        g = self.image_buffer[index * 3 + 1]
        b = self.image_buffer[index * 3 + 2]
        return (r, g, b)

    def get_image_pixel_sync(self, x, y):
        with self.sync_lock:
            return self.get_image_pixel(x, y)

    def set_image_pixel(self, x, y, rgb):
        index = y * self.width + x
        self.image_buffer[index * 3] = rgb[0]
        self.image_buffer[index * 3 + 1] = rgb[1]
        self.image_buffer[index * 3 + 2] = rgb[2]

    def set_image_pixel_sync(self, x, y, rgb):
        raise NotImplemented

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

    def get_task(self, func):
        with self.sync_lock:
            task = func(self)
        return task

    def on_open(self, ws):
        ws.send(token)

        # Avoid creating multiple heart beat thread
        if self.heart_beat_thread and self.heart_beat_thread.is_alive():
            return

        self.heart_beat_thread = threading.Thread(
            target=self.thread_func_heart_beat)
        self.heart_beat_thread.daemon = True
        self.heart_beat_thread.start()

    def on_message(self, ws, message):
        # TODO: force full update after certain amount of time
        try:
            message_header = MessageHeader._make(
                message_header_struct.unpack_from(message)
            )
            if message_header.opcode == 3:
                print("[INFO] online message")
            elif message_header.opcode == 5:
                print("[INFO] receive %d bytes data for decoding" %
                      len(message))
                self.process_message(message)
            elif message_header.opcode == 8:
                print("[INFO] receive heart beat request")
                self.heart_beat()
            else:
                print("[INFO] Unkown opcode %d" % message_header.opcode)
        except Exception as e:
            print("[ERROR] cannot decode message format: %s" % e)
            return

    def process_message(self, message):
        update_list = []
        offset = 0
        while offset < len(message):
            try:
                message_header = MessageHeader._make(
                    message_header_struct.unpack_from(message, offset)
                )
                data = message[offset + message_header.start_offset:offset +
                               message_header.end_offset]
                message_object = json.loads(data)

                cmd = message_object['cmd']
                if cmd == "DRAW_UPDATE":
                    x = message_object['data']['x_max']
                    y = message_object['data']['y_max']
                    color_code = message_object['data']['color']
                    rgb = hex_to_rgb(code_map[color_code])
                    update_list.append([x, y, rgb])

                    print("@%s, cmd: %s, update (%d, %d) with color %s" %
                          (datetime.now(), cmd, x, y, color_code))
                else:
                    print("@%s, Other message: %s" % (datetime.now(), data))

                offset += message_header.end_offset

            except Exception as e:
                print("Error occurs in process_message: %s" % e)
                print("Error message(offset: %d): %s," % (offset, message))
                print("Error message(bytearray): %r" % bytearray(message))
                break

        # finally update the pixels in critical section
        start_time = time.clock()
        with self.sync_lock:
            for x, y, rgb in update_list:
                self.set_image_pixel(x, y, rgb)
        print("[DEBUG] update pixels in %.6f" % (time.clock() - start_time))

    def on_error(self, ws, error):
        """
        Generally speaking, on_close will be invoked after on_error
        """
        print("[ERROR]@%s, on_error is called with: %s" %
              (datetime.now(), error))

    def on_close(self, ws):
        """
        We need rerun the WebSocket loop in another thread. Because we are
        currently at the end of a WebSocket loop running inside
        self.ws_loop_thread.

        DO NOT join on that thread, that is the current thread
        """
        print("[ERROR]@%s, on_close is called" % (datetime.now()))
        print("[INFO] WebSocket is closed after running %.2f seconds" %
              (time.time() - self.start_time))

        # Force a full update
        self.update_image()

        # when on_close returns, the run_forever method also returns. Then
        # while True loop in self.ws_loop_thread will execute run_forever
        # again, and it will reconnect to the server

        # on_close means the WebSocket loop thread is terminating, we need to
        # restart the loop in another thread
#         if self.enable_reconnect:
#
#             def restart_websocket():
#                 print("[INFO] restart WebSocket connection")
#                 print("[INFO] waiting for previous WebSocket event loop"
#                       " to be terminated")
#                 self.ws_loop_thread.join()
#                 print("[INFO] previous WebSocket event loop is terminated")
#                 self.update_image_with_incremental_update()
#                 print("[INFO] restart thread is terminated")

        # we need to join on the previous event loop thread to ensure it
        # is really terminated
        # restart_thread = threading.Thread(target=restart_websocket)
        # restart_thread.daemon = True
        # restart_thread.start()

    def heart_beat(self):
        print("[DEBUG] Sending heart beat")
        self.ws.send(heart_beat)

    def start_websocket(self):
        assert self.ws_loop_thread is None or \
            not self.ws_loop_thread.is_alive(), \
            "Previous WebSocket event loop thread is not terminated"

        # execute ws.run_forever infinitely
        def run(ws):
            while True:
                try:
                    print("[DEBUG] start ws.run_forever")
                    ws.run_forever()
                    print("[DEBUG] ws.run_forever terminates")
                except Exception as e:
                    print("ws.run_forever(): %s" % e)

        self.ws_loop_thread = threading.Thread(target=run, args=(self.ws, ))
        self.ws_loop_thread.daemon = True
        self.ws_loop_thread.start()

    def thread_func_heart_beat(self):
        while True:
            try:
                self.heart_beat()
            except websocket.WebSocketConnectionClosedException:
                # ws_loop_thread will reconnect to server soon
                print("[ERROR] WebSocket connection is already closed")
                # break
            except Exception as e:
                print("[ERROR] heart beat thread has error: %e" % e)
                # break
            time.sleep(30)
        print("[INFO] heart beat threat exit")

    def update_image_with_incremental_update(self):
        self.start_time = time.time()
        self.update_image()
        self.start_websocket()


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
