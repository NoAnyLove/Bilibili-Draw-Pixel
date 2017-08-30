import asyncio
import collections
import aiohttp
import struct
import time
import json
from PIL import Image
from util import CODE_COLOR_TABLE, hex_to_rgb, CODE_RGB_TABLE
import logger

__all__ = ["UpdateImage"]

FULL_UPDATE_URL = r"http://api.live.bilibili.com/activity/v1/SummerDraw/bitmap"

TOKEN = bytearray([0x00, 0x00, 0x00, 0x27, 0x00, 0x10, 0x00, 0x01, 0x00, 0x00,
                   0x00, 0x07, 0x00, 0x00, 0x00, 0x01, 0x7B, 0x22, 0x75, 0x69,
                   0x64, 0x22, 0x3A, 0x30, 0x2C, 0x22, 0x72, 0x6F, 0x6F, 0x6D,
                   0x69, 0x64, 0x22, 0x3A, 0x35, 0x34, 0x34, 0x36, 0x7D])

HEART_BEAT_TOKEN = bytearray([0x00, 0x00, 0x00, 0x10, 0x00, 0x10, 0x00, 0x01,
                              0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x01])

LOGGER = logger.get_logger('update_image')

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
    def __init__(self, *, lazy_threshold=60, task_queue=None,
                 guard_region=None, guard_priority=None, loop=None,
                 connector=None):
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.task_queue = task_queue
        self.guard_region = guard_region
        self.guard_priority = guard_priority
        # reuse the same TCPConnector
        self.connector = connector
        self.session = aiohttp.ClientSession(loop=loop, connector=connector)

        self.full_update_callback = None

        self.width = 1280
        self.height = 720
        self.image_buffer = bytearray(self.width * self.height * 3)
        self.last_update = None
        self.lazy_threshold = lazy_threshold
        self.timeout = 30
        self.defualt_priority = 0

        self.async_lock = asyncio.Lock(loop=loop)
        self.enable_reconnect = True
        self.websocket_task = None
        self.heart_beat_task = None
        self.guard_region_callback = None

    async def perform_update_image(self):
        """ Avoid invoking this method in different threads
        """
        LOGGER.info("Downloading %s" % FULL_UPDATE_URL)
        try:
            r = await self.session.get(FULL_UPDATE_URL, timeout=self.timeout)
        except aiohttp.ClientConnectionError:
            LOGGER.error("Failed to connect to Bilibili.com")
            return
        except aiohttp.ServerTimeoutError:
            LOGGER.error("Connection timeout, failed to update image")
            return
        except Exception as e:
            LOGGER.error("Error occurs: %s", e)
            return
        try:
            data = await r.json()
            code_data = data["data"]["bitmap"]
        except Exception as e:
            LOGGER.error("Failed to update image with error: %s" % e)
            return

        if not isinstance(code_data, str):
            LOGGER.error("Incorrect code data: %s" % code_data)
            return
        if len(code_data) != self.width * self.height:
            LOGGER.error("Code data length mismatch: %d" % len(code_data))

        convert_code_to_bytes(CODE_COLOR_TABLE, code_data, self.image_buffer)
        self.last_update = time.time()

        if self.full_update_callback is not None:
            self.full_update_callback()

    async def async_lazy_update_image(self):
        ret = -1
        start_time = time.time()

        async with self.async_lock:
            if self.last_update is None:
                await self.perform_update_image()
            elif time.time() > self.last_update + self.lazy_threshold:
                await self.perform_update_image()
            else:
                ret = self.last_update
        end_time = time.time()
        if ret == -1:
            LOGGER.debug("update image in %.2fs" %
                         (end_time - start_time))
        else:
            LOGGER.debug("lazily updated %.2fs before" %
                         (end_time - ret))
        return ret

    def get_image_pixel(self, x, y):
        index = (y * self.width + x) * 3
        return tuple(self.image_buffer[index:index + 3])

    def set_image_pixel(self, x, y, rgb):
        index = (y * self.width + x) * 3
        self.image_buffer[index:index + 3] = rgb

    def save_buffer_to_file(self, filename):
        img = Image.frombytes("RGB", (1280, 720), bytes(self.image_buffer))
        try:
            img.save(filename, "GIF")
        except Exception as err:
            LOGGER.error("Failed to save file %s with error: %s" %
                         (filename, err))

    def get_task(self, func):
        task = func(self)
        return task

    def on_message(self, message):
        # TODO: force full update after certain amount of time
        try:
            message_header = MessageHeader._make(
                message_header_struct.unpack_from(message)
            )
            if message_header.opcode == 3:
                LOGGER.debug("received online message")
            elif message_header.opcode == 5:
                LOGGER.debug("received %d bytes message data" %
                             len(message))
                self.process_message(message)
            elif message_header.opcode == 8:
                LOGGER.debug("received heart beat request")
            else:
                LOGGER.warning("received data with unknown opcode %d" %
                               message_header.opcode)
        except Exception as e:
            LOGGER.warning("cannot decode message: %s" % e)
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
                    update_list.append([x, y, color_code])

                    LOGGER.debug(
                        "cmd: %s, update (%d, %d) with color %s" %
                        (cmd, x, y, color_code))
                else:
                    LOGGER.debug("Other message: %s" %
                                 (data))

                offset += message_header.end_offset

            except Exception as err:
                LOGGER.error("Error message (offset: %d): %s, err: %s" %
                             (offset, message, err))
                break

        # finally update the pixels in critical section
        start_time = time.clock()
        for x, y, color_code in update_list:
            rgb = CODE_RGB_TABLE[color_code]
            self.set_image_pixel(x, y, rgb)
            # ignore when guard_region is not used
            if self.guard_region is None:
                continue
            # check guard region
            if (x, y) in self.guard_region:
                desired_color_code = self.guard_region[(x, y)]
                if desired_color_code != color_code:
                    LOGGER.info("(%d, %d) %s triggers the guard region",
                                x, y, color_code)

                    self.task_queue.put_nowait(
                        (self.get_task_priority(x, y),
                         x,
                         y,
                         desired_color_code)
                    )

        LOGGER.debug("process_message update pixels in %.6f" %
                     (time.clock() - start_time))

    def on_error(self):
        """
        Generally speaking, on_close will be invoked after on_error
        """
        LOGGER.error("on_error is called")

    def on_close(self):
        """
        We need rerun the WebSocket loop in another thread. Because we are
        currently at the end of a WebSocket loop running inside
        self.ws_loop_thread.

        DO NOT join on that thread, that is the current thread
        """
        LOGGER.error("on_close is called")
        LOGGER.info("WebSocket is closed after running %.2f seconds" %
                    (time.time() - self.start_time))

    async def heart_beat(self):
        while True:
            LOGGER.debug("Sending heart beat")
            await self.ws.send_bytes(HEART_BEAT_TOKEN)
            await asyncio.sleep(30)

    async def start_websocket(self):
        async with self.session.ws_connect(
                r"ws://broadcastlv.chat.bilibili.com:2244/sub") as ws:
            self.ws = ws
            await ws.send_bytes(TOKEN)
            self.heart_beat_task = asyncio.ensure_future(self.heart_beat())
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    self.on_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self.on_close()
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.on_error()

        # cancel previous heart beat coroutine
        if self.heart_beat_task:
            self.heart_beat_task.cancel()

        # force a full update and reconnect WebSocket
        if self.enable_reconnect:
            LOGGER.info("reconnecting WebSocket")
            await self.perform_update_image()
            self.websocket_task = asyncio.ensure_future(self.start_websocket())

    def close(self):
        if self.heart_beat_task:
            self.heart_beat_task.cancel()
        if self.websocket_task:
            self.websocket_task.cancel()
        if self.session:
            self.session.close()

    def get_task_priority(self, x, y):
        if self.guard_priority is None:
            return self.defualt_priority
        else:
            return self.guard_priority.get((x, y), self.defualt_priority)


def convert_code_to_bytes(CODE_COLOR_TABLE, code_data, buf):
    i = 0
    for code in code_data:
        rgb_hex = CODE_COLOR_TABLE[code]
        rgb = hex_to_rgb(rgb_hex)
        buf[i:i + 3] = rgb
        i += 3
    return buf
