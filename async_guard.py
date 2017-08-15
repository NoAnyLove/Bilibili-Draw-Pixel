#!/usr/bin/env python3

import json
from datetime import datetime
import functools
import sys
import asyncio
import collections
import aiohttp
from async_update_image import AsyncUpdateImage
from util import process_tasks, RGB_CODE_TABLE, CODE_RGB_TABLE,\
    async_draw_pixel_with_requests, extract_cookies, process_status_101


def find_all_polluted_pixels(tasks_dict, up):
    """This method will be called inside critical section
    """
    polluted_tasks = []
    for (x, y), color_code in tasks_dict.items():
        rgb = CODE_RGB_TABLE[color_code]
        if rgb != up.get_image_pixel(x, y):
            polluted_tasks.append((x, y, color_code))
    return polluted_tasks


async def task_main(worker_id, user_id, session, task_queue, up,
                    user_counters, workers):
    print("<worker-%s> start working" % worker_id)
    wait_time = -1
    while True:
        x, y, color_code = await task_queue.get()
        while True:
            # check if it is already the correct color_code
            current_rgb = up.get_image_pixel(x, y)
            current_color_code = RGB_CODE_TABLE[current_rgb]
            wait_time = -1
            if current_color_code == color_code:
                print("@%s, <worker-%s> skip correct pixel (%d, %d)" %
                      (datetime.now(), worker_id, x, y))
                break

            # output may be an empty string
            print("<worker-%s> start to draw (%d, %d)" % (worker_id, x, y))

            status_code, wait_time, cost_time = \
                await async_draw_pixel_with_requests(session, x, y, color_code)

            if status_code == 0:
                print("@%s, <worker-%s> draw (%d, %d) with %s, status:"
                      " %d, cost %.2fs" %
                      (datetime.now(), worker_id,
                       x, y, color_code, status_code, cost_time))
            elif status_code == -101:
                process_status_101(user_counters, worker_id,
                                   user_id, cost_time, workers)
            else:
                print("@%s, <worker-%s> draw (%d, %d), status: %s, "
                      "retry after %ds, cost %.2fs"
                      % (datetime.now(), worker_id, x, y,
                          status_code, wait_time, cost_time))

            # sleep for cool-down time
            if wait_time > 0:
                await asyncio.sleep(wait_time)


def main():
    if len(sys.argv) == 3:
        tasks_filename = sys.argv[1]
        user_filename = sys.argv[2]
    else:
        print("Usage: %s task_file user_file" % sys.argv[0])
        sys.exit()

    with open(tasks_filename, "r") as fp:
        tasks = json.load(fp)

    # convert missing colors to available colors, and convert RGB hex to
    # one-character color code
    tasks_dict = process_tasks(tasks)
    user_counters = collections.defaultdict(int)
    loop = asyncio.get_event_loop()
    connector = aiohttp.TCPConnector(loop=loop)
    # TODO: use PriorityQueue to have better control of tasks
    task_queue = asyncio.Queue(loop=loop)

    up = AsyncUpdateImage()
    up.full_update_callback = functools.partial(
        populate_tasks, tasks_dict, up, task_queue)
    # enable reactive guard
    up.task_queue = task_queue
    up.guard_region = tasks_dict

    session_list = []
    with open(user_filename, "r") as fp:
        for user_cmd in fp:
            # Skip comments
            if user_cmd.startswith('#'):
                continue
            # Skip empty line
            user_cmd = user_cmd.strip()
            if not user_cmd:
                continue
            user_cookies = extract_cookies(user_cmd)
            session_list.append((
                user_cookies,
                aiohttp.ClientSession(
                    connector=connector,
                    loop=loop,
                    cookies=user_cookies,
                    connector_owner=False),
            ))

    print('[INFO] loaded %d accounts' % len(session_list))

    # Load plugin clock
    import clock
    clock_plugin = clock.ClockPlugin(loop, tasks_dict, up, task_queue)
    clock_plugin.enable()

    loop.run_until_complete(up.async_update_image())
    # TODO
    # websocket_task = asyncio.ensure_future(up.start_websocket())
    asyncio.ensure_future(up.start_websocket())

    workers = [None] * len(session_list)
    for worker_id, (user_cookies, session) in enumerate(session_list):
        workers[worker_id] = asyncio.Task(
            task_main(worker_id, user_cookies['DedeUserID'], session,
                      task_queue, up, user_counters, workers),
            loop=loop
        )

    try:
        loop.run_forever()
        print("Finished all tasks, existing")
    except KeyboardInterrupt:
        print("Ctrl-c pressed, exiting")

        # cancel all running tasks
        all_tasks = asyncio.Task.all_tasks()
        for task in all_tasks:
            task.cancel()
        # this line is necessary to avoid the "Task was destroyed but it is
        # pending!" warning
        loop.run_until_complete(asyncio.gather(*all_tasks))
    finally:
        up.close()
        connector.close()
        loop.stop()
        loop.close()
        sys.exit()


def populate_tasks(tasks_dict, up, task_queue):
    find_func = functools.partial(find_all_polluted_pixels, tasks_dict)
    polluted_pixels = up.get_task(find_func)
    for task in polluted_pixels:
        task_queue.put_nowait(task)


if __name__ == "__main__":
    main()