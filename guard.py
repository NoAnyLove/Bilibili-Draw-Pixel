import time
import json
import random
from datetime import datetime
import sys
from update_image import UpdateImage
from util import hex_to_rgb, process_task_missing_color, \
    draw_pixel_with_requests, extract_cookies, process_status_101
import functools
import threading


def find_a_polluted_pixel(tasks, up):
    """This method will be called inside critical section
    """
    for x, y, rgb_hex in tasks:
        rgb = hex_to_rgb(rgb_hex)
        if rgb != up.get_image_pixel(x, y):
            # modify image to avoid return the same pixel
            up.set_image_pixel(x, y, rgb)
            # return the corresponding task with polluted pixel
            return x, y, rgb_hex
    return None


def thread_main(user_id, user_cmd, tasks, up, use_incremental_update):
    # improve the thread output at the beginning
    time.sleep(3 + random.random())

    # used to count the number of occurrence of code -101
    invalid_cookie_counter = [0]

    print("%s start working" % user_id)
    interval = 60
    # cmd_template = process_cmd_template(user_cmd)
    user_cookies = extract_cookies(user_cmd)
    find_func = functools.partial(find_a_polluted_pixel, tasks)
    while True:
        if not use_incremental_update:
            up.lazy_update_image()

        start_time = time.time()
        # get_task will call find_func in critical section
        task = up.get_task(find_func)
        print("<%s> up.get_task returns in %.2f" %
              (user_id, time.time() - start_time))
        if task is not None:
            x, y, rgb_hex = task
        else:
            print("@%s, <%s> no polluted pixel is found, sleep %ds" %
                  (datetime.now(), user_id, interval))
            time.sleep(interval)
            continue

        print("<%s> start to draw (%d, %d)" % (user_id, x, y))

        status_code, wait_time, cost_time = draw_pixel_with_requests(
            user_cookies, x, y, rgb_hex)

        if status_code == 0:    # draw successfully
            print("@%s, <%s> draw (%d, %d) with %s, status: %d,"
                  " cost %.2fs" %
                  (datetime.now(), user_id,
                   x, y, rgb_hex, status_code, cost_time))
#         elif status_code == -400:   # not ready to draw a new pixel
#             print("@%s, <%s> draw (%d, %d), status: %d, "
#                   "retry after %ds, cost %.2fs"
#                   % (datetime.now(), user_id, x, y,
#                       status_code, wait_time, cost_time))
        elif status_code == -101:
            process_status_101(invalid_cookie_counter,
                               user_id, cost_time, user_cookies)
        else:
            print("@%s, <%s> draw (%d, %d) with status: %s, "
                  "retry after %ds, cost %.2fs"
                  % (datetime.now(), user_id, x, y,
                      status_code, wait_time, cost_time))

        if wait_time > 0:
            time.sleep(wait_time)


if __name__ == "__main__":
    if len(sys.argv) == 3:
        tasks_filename = sys.argv[1]
        user_filename = sys.argv[2]
    else:
        print("Usage: %s task_file user_file" % sys.argv[0])
        sys.exit()

    with open(tasks_filename, "r") as fp:
        tasks = json.load(fp)

    # convert missing colors to available colors
    process_task_missing_color(tasks)

    # TODO: flag
    use_incremental_update = True
    up = UpdateImage()
    if use_incremental_update:
        up.update_image_with_incremental_update()
    thread_list = []
    count = 1
    with open(user_filename, "r") as fp:
        for user_cmd in fp:
            # Skip comments
            if user_cmd.startswith('#'):
                continue
            # Skip empty line
            user_cmd = user_cmd.strip()
            if not user_cmd:
                continue

            user_id = "User-%d" % count
            count += 1
            thread = threading.Thread(
                target=thread_main,
                args=(user_id, user_cmd, tasks, up, use_incremental_update))
            thread.daemon = True
            thread.start()
            thread_list.append(thread)

    print('[INFO] loaded %d accounts' % (count - 1))

    last_update_time = time.time()
    force_full_update_interval = 3600
    # run forever, until Ctrl+C is pressed
    while True:
        try:
            time.sleep(30)

            if time.time() - last_update_time >= force_full_update_interval:
                print("[INFO] force full update after %d seconds" %
                      force_full_update_interval)
                up.update_image()
                last_update_time = time.time()

        except KeyboardInterrupt:
            print("Ctrl-c pressed, exiting")
            sys.exit()
