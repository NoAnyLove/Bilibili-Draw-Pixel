import time
import json
import re
from datetime import datetime
import sys
from update_image import UpdateImage
from util import hex_to_rgb, process_task_missing_color, \
    draw_pixel_with_requests, extract_cookies
import functools
import threading


def process_cmd_template(cmd_template):
    pattern = r"--data '.+'"
    tp = r"--data 'x_min={x}&y_min={y}&x_max={x}&y_max={y}&color={color}'"
    cmd_template = re.sub(pattern, tp, cmd_template)

    pattern = r"curl '"
    tp = r"curl -s '"
    cmd_template = re.sub(pattern, tp, cmd_template)
    return cmd_template


def find_a_polluted_pixel(tasks, up):
    for x, y, rgb_hex in tasks:
        rgb = hex_to_rgb(rgb_hex)
        if rgb != up.get_image_pixel(x, y):
            # modify image to avoid return the same pixel
            up.set_image_pixel(x, y, rgb)
            # return the corresponding task with polluted pixel
            return x, y, rgb_hex
    return None


def thread_main(user_id, user_cmd, tasks, up):
    print("%s start working" % user_id)
    interval = 60
    # cmd_template = process_cmd_template(user_cmd)
    user_cookies = extract_cookies(user_cmd)
    find_func = functools.partial(find_a_polluted_pixel, tasks)
    while True:
        up.lazy_update_image()
        start_time = time.time()
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
        # output may be an empty string
        output, cost_time = draw_pixel_with_requests(
            user_cookies, x, y, rgb_hex)

        # sometimes failed to get json
        try:
            status = None
            status = json.loads(output)
            wait_time = status['data']['time']
            status_code = status['code']
        except Exception:
            print("@%s, <%s> failed to draw (%d, %d), wrong JSON"
                  " response: %s" %
                  (datetime.now(), user_id, x, y, status))
            continue

        if status_code == 0:
            print("@%s, <%s> draw (%d, %d) with %s, status: %d,"
                  " cost %.2fs" %
                  (datetime.now(), user_id,
                   x, y, rgb_hex, status_code, cost_time))
        else:
            print("@%s, <%s> draw (%d, %d), status: %d, "
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

    up = UpdateImage()
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
                args=(user_id, user_cmd, tasks, up))
            thread.daemon = True
            thread.start()
            thread_list.append(thread)

    print('[INFO] loaded %d accounts' % (count - 1))

    # run forever, until Ctrl+C is pressed
    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            print("Ctrl-c pressed, exiting")
            sys.exit()
