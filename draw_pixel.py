#!/usr/bin/env python3

import json
import sys
import asyncio
import collections
from update_image import UpdateImage
import logger
from util import process_tasks, RGB_CODE_TABLE,\
    async_draw_pixel_with_requests, extract_cookies, process_status_101
import aiohttp


LOGGER = logger.get_logger('guard')


async def task_main(worker_id, user_id, session, task_queue, total, up,
                    user_counters, workers):
    LOGGER.info("<worker-%s> start working" % worker_id)
    wait_time = -1
    while True:
        index, x, y, color_code = await task_queue.get()
        while True:
            # check if it is already the correct color_code
            current_rgb = up.get_image_pixel(x, y)
            current_color_code = RGB_CODE_TABLE[current_rgb]
            wait_time = -1
            if current_color_code == color_code:
                LOGGER.debug(
                    "[%d/%d] <worker-%s> skip correct pixel (%d, %d)" %
                    (index, total, worker_id, x, y))
                task_queue.task_done()
                break

            # output may be an empty string
            LOGGER.debug("<worker-%s> start to draw (%d, %d)" %
                         (worker_id, x, y))

            status_code, wait_time, cost_time = \
                await async_draw_pixel_with_requests(session, x, y, color_code)

            if status_code == 0:
                LOGGER.info(
                    "[%d/%d] <worker-%s> draw (%d, %d) with %s, status:"
                    " %d, cost %.2fs" %
                    (index, total, worker_id, x, y, color_code, status_code, cost_time))
                task_queue.task_done()
            elif status_code == -101:
                process_status_101(user_counters, worker_id,
                                   user_id, cost_time, workers)
            else:
                LOGGER.info("[%d/%d] <worker-%s> draw (%d, %d), status: %s, "
                            "retry after %ds, cost %.2fs"
                            % (index, total, worker_id, x, y,
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
    total_task = len(tasks_dict)
    user_counters = collections.defaultdict(int)
    loop = asyncio.get_event_loop()
    connector = aiohttp.TCPConnector(loop=loop)
    # TODO: use PriorityQueue to have better control of tasks
    task_queue = asyncio.Queue(loop=loop)

    for index, ((x, y), color_code) in enumerate(tasks_dict.items(), 1):
        task_queue.put_nowait((index, x, y, color_code))

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

    LOGGER.critical('[INFO] loaded %d accounts' % len(session_list))

    up = UpdateImage()
    loop.run_until_complete(up.perform_update_image())
    asyncio.ensure_future(up.start_websocket())

    workers = [None] * len(session_list)
    for worker_id, (user_cookies, session) in enumerate(session_list):
        workers[worker_id] = asyncio.Task(
            task_main(worker_id, user_cookies['DedeUserID'], session,
                      task_queue, total_task, up, user_counters, workers),
            loop=loop
        )

    try:
        loop.run_until_complete(asyncio.ensure_future(task_queue.join()))
        # loop.run_forever()
        LOGGER.critical("Finished all tasks, existing")
    except KeyboardInterrupt:
        print("Ctrl-c pressed, exiting")
        up.close()
    finally:
        # cancel all running tasks
        all_tasks = asyncio.Task.all_tasks()
        for task in all_tasks:
            task.cancel()
        # this line is necessary to avoid the "Task was destroyed but it is
        # pending!" warning. The Task.cancel() method arranges for a
        # CancelledError to be thrown in the next cycle of event loop, we need
        # to give the event loop a chance to finish this.
        try:
            loop.run_until_complete(asyncio.gather(*all_tasks))
        except asyncio.CancelledError:
            pass
        up.close()
        connector.close()
        loop.stop()
        loop.close()
        sys.exit()


if __name__ == "__main__":
    main()
