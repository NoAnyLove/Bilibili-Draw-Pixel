import subprocess
import time
import json
import re
from datetime import datetime
import sys
from update_image import UpdateImage
from util import hex_to_rgb, rgb_hex_to_color_code, process_task_missing_color
import functools


def draw_pixel(cmd_template, x, y, rgb_hex):
    color_code = rgb_hex_to_color_code(rgb_hex)
    try:
        start_time = time.time()
        output = subprocess.check_output(cmd_template.format(
            **{'x': x, 'y': y, 'color': color_code}), shell=True)
    except Exception:
        output = ''
    return output, time.time() - start_time


def process_cmd_template(cmd_template):
    pattern = r"--data '.+'"
    tp = r"--data 'x_min={x}&y_min={y}&x_max={x}&y_max={y}&color={color}'"
    cmd_template = re.sub(pattern, tp, cmd_template)

    pattern = r"curl '"
    tp = r"curl -s '"
    cmd_template = re.sub(pattern, tp, cmd_template)
    return cmd_template


# def thread_main(user_cmd, tasks):
#     print("start working")
#     up = update_image.UpdateImage()
#     up.update_image(True)
#     # make sure template string is correct
#     cmd_template = process_cmd_template(user_cmd)
#     total = len(tasks)
#     for index, (x, y, color) in enumerate(tasks, 1):
#         while True:
#             # check if it is already the correct color
#             cur_rgb = up.get_image_pixel(x, y)
#             cur_rgb_hex = rgb_to_hex(*cur_rgb)
#             wait_time = -1
#             if cur_rgb_hex == color:
#                 print("[%d/%d] @%s, skip correct pixel (%d, %d)" %
#                       (index, total, datetime.now(), x, y))
#                 break
#
#             output = draw_pixel(cmd_template, x, y, color)
#             status = json.loads(output)
#             wait_time = status['data']['time']
#             if status['code'] == 0:
#                 print("[%d/%d] @%s, draw (%d, %d) with %s, status: %d" %
#                       (index, total, datetime.now(), x, y, color,
#                        status['code']))
#                 break
#             else:
#                 print("[%d/%d] @%s, draw (%d, %d), status: %d, retry after %ds"
#                       % (index, total, datetime.now(), x, y,
#                           status['code'], wait_time))
#                 time.sleep(wait_time)
#
#         # sleep for cool-down interval
#         time_span = 10
#         if wait_time > time_span:
#             time.sleep(wait_time - time_span)
#             start_time = time.time()
#             up.update_image(True)
#             end_time = time.time()
#             print("update image in %.2fs" % (end_time - start_time))
#             if end_time - start_time < time_span:
#                 time.sleep(time_span - (end_time - start_time))
#         elif wait_time > 0:
#             time.sleep(wait_time)

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
    cmd_template = process_cmd_template(user_cmd)
    find_func = functools.partial(find_a_polluted_pixel, tasks)
    while True:
        up.update_image()
        task = up.get_task(find_func)
        if task is not None:
            x, y, rgb_hex = task
        else:
            print("@%s, <%s> find no polluted pixel, sleep %ds" %
                  (datetime.now(), user_id, interval))
            time.sleep(interval)
            continue

        print("<%s> start to draw (%d, %d)" % (user_id, x, y))
        # output may be an empty string
        output, cost_time = draw_pixel(cmd_template, x, y, rgb_hex)

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

    if user_filename is not None:
        with open(user_filename, "r") as fp:
            user_cmd = fp.readline().strip()

    up = UpdateImage()
    thread_main("user-1", user_cmd, tasks, up)