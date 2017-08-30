import asyncio
import enum
import zlib
import pendulum
import logger
from util import RGB_CODE_TABLE

__all__ = ['ClockPlugin']

BASE_LEFT = 325
BASE_TOP = 179
BASE_X = 15
BASE_Y = 6
IMG_LENGTH = 52
LENGTH = 12 * 3

AM = (63, 81, 181)
PM = (244, 67, 54)

IMAGE_DATA = bytearray(zlib.decompress(
    b'x\x9c[\xb5jP\x83\x1f\xa7{ \x88\xb5p\xfa\xff\x19\x0cx\x10\x1c\x80\xb8@'
    b'\x80,\x02\x03\x10Y4\x11L5h"P-3\x18\xe0\\\x88\xdb\x80\x0c\xa0\xc3\xe0\x0e'
    b'\x80\xb0!$\xd0\xb5\x10\x04w\x1b\x8a\xbdHn\x86\xb2\xd1\xdc\x86&\x8bK\r6'
    b'\x114\xb7\x01\xdd\x80\xec0xHbq\x1b\xdep\xc3)\x82\xe46\x82\xba\x88q\x1b'
    b'\xf6pCr\x1bZ\x98\xe0\x0bIbDH\x0c7,\xe9\ro\xca\xc1\x99\xde\xf0\x86\x1bZ'
    b'j!5\xdc\xe8\x89\xe8[\x1e\x90\x0c\x00\x1e\xda\xb44'
))


LOGGER = logger.get_logger("Plugin.Clock")


@enum.unique
class HourStage(enum.Enum):
    s0 = (0, 9, '1000', 's1')
    s1 = (10, 19, '1100', 's2')
    s2 = (20, 29, '0100', 's3')
    s3 = (30, 39, '0110', 's4')
    s4 = (40, 49, '0010', 's5')
    s5 = (50, 59, '0011', 's0')

    def __init__(self, start, end, mask, next_stage):
        self.start = start
        self.end = end
        self.mask = mask
        self.next_stage = next_stage

    def __contains__(self, minute):
        return self.start <= minute <= self.end

    def step(self):
        for stage in HourStage:
            if stage.name == self.next_stage:
                return stage


class ClockPlugin(object):
    def __init__(self, loop, tasks_dict, priority_dict, up, task_queue):
        self.loop = loop
        self.tasks_dict = tasks_dict
        self.up = up
        self.task_queue = task_queue
        self.priority_dict = priority_dict
        self.defualt_priority = -1
        LOGGER.debug("Plugin Clock is loaded")

    def enable(self):
        wait_time = self.process_tasks()
        self.loop.call_later(wait_time, self.start)
        LOGGER.info("Plugin Clock is started")

    def process_tasks(self):
        clock_tasks, wait_time = self.generate_tasks()
        tasks_dict = self.tasks_dict
        priority_dict = self.priority_dict
        defualt_priority = self.defualt_priority
        # update original tasks_dict
        # TODO: need to check if this task is in tasks_dict
        for x, y, color_code in clock_tasks:
            LOGGER.debug("Updating task (%d, %d) with %s" %
                         (x, y, color_code))
            tasks_dict[(x, y)] = color_code
            priority_dict[(x, y)] = defualt_priority
        return wait_time

    def start(self):
        asyncio.ensure_future(self.work())

    def generate_tasks(self):
        tasks = []
        now = pendulum.now('Asia/Shanghai')
        hour = now.hour
        if hour >= 12:
            color = PM
            hour %= 12
        else:
            color = AM

        minute = now.minute
        current_stage = None
        for stage in HourStage:
            if minute in stage:
                current_stage = stage
                break

        LOGGER.info("Clock is in stage %s" % (current_stage.name))

        index = (BASE_Y * IMG_LENGTH + BASE_X) * 3
        slice_image_data = IMAGE_DATA[index:index + LENGTH * 3]

        # build the time line
        index = hour * 3
        for digit in current_stage.mask:
            if digit == '1':
                slice_image_data[index * 3:index * 3 + 3] = color
            index += 1
            if index >= LENGTH:
                index %= LENGTH

        y = BASE_Y
        for x in range(0, LENGTH):
            index = x * 3
            desired_rgb = tuple(slice_image_data[index:index + 3])
            desired_code = RGB_CODE_TABLE[desired_rgb]
            index = ((y + BASE_TOP) * self.up.width +
                     BASE_X + BASE_LEFT + x) * 3
            current_rgb = tuple(self.up.image_buffer[index:index + 3])
            real_x = BASE_LEFT + BASE_X + x
            real_y = BASE_TOP + y
            if desired_rgb != current_rgb:
                # print("[CLOCK] not match (%d,%d) des %s, cur %s" %
                #      (real_x, real_y, desired_rgb, current_rgb))
                tasks.append((real_x, real_y, desired_code))

            if self.up.guard_region:
                self.up.guard_region[(real_x, real_y)] = desired_code

        next_stage = current_stage.step()
        if next_stage == HourStage.s0:
            hour = now.hour + 1
        else:
            hour = now.hour
        if hour >= 24:
            hour %= 24
            next_time = now.add(days=1)
        else:
            next_time = now.copy()

        next_time = next_time.replace(
            hour=hour, minute=next_stage.start, second=0)

        wait_time = (next_time - now).in_seconds()
        LOGGER.debug("now=%s, next_time=%s, wait_time=%s" %
                     (now, next_time, wait_time))

        # asyncio.sleep may not return exactly at the expected time. If we want
        # to wake up at 10:00:00, but actually wake up at 09:59:xx, it might
        # cause a busy loop. To mitigate this problem, we force the minimum
        # wait time to be 10 seconds
        wait_time = max(10, wait_time)

        return tasks, wait_time

    async def work(self):
        task_queue = self.task_queue
        default_priority = self.defualt_priority - 1
        while True:
            tasks, wait_time = self.generate_tasks()
            for x, y, color_code in tasks:
                LOGGER.debug("Adding task pri:%d (%d, %d) %s" %
                             (default_priority, x, y, color_code))
                task_queue.put_nowait(
                    (default_priority,
                     x,
                     y,
                     color_code)
                )

            await asyncio.sleep(wait_time)
