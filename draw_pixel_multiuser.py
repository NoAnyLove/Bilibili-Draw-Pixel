import subprocess
import time
import json
import re
from datetime import datetime
import sys
import Queue
import threading
from update_image import UpdateImage
from util import rgb_hex_to_color_code, rgb_to_hex


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


def thread_main(user_id, user_cmd, task_queue, total, up):
    print("%s start working" % user_id)
    cmd_template = process_cmd_template(user_cmd)
    while True:
        index, (x, y, color) = task_queue.get()
        while True:
            # check if it is already the correct color
            cur_rgb = up.get_image_pixel(x, y)
            cur_rgb_hex = rgb_to_hex(*cur_rgb)
            wait_time = -1
            if cur_rgb_hex == color:
                print("[%d/%d] @%s, <%s> skip correct pixel (%d, %d)" %
                      (index, total, datetime.now(), user_id, x, y))
                task_queue.task_done()
                break

            # output may be an empty string
            print("<%s> start to draw (%d, %d)" % (user_id, x, y))
            output, cost_time = draw_pixel(cmd_template, x, y, color)

            # sometimes failed to get json
            try:
                status = json.loads(output)
            except Exception:
                print("[%d/%d] @%s, <%s> failed to draw (%d, %d)" %
                      (index, total, datetime.now(), user_id, x, y))
                continue

            wait_time = status['data']['time']
            if status['code'] == 0:
                print("[%d/%d] @%s, <%s> draw (%d, %d) with %s, status: %d,"
                      " cost %.2fs" %
                      (index, total, datetime.now(), user_id,
                       x, y, color, status['code'], cost_time))
                task_queue.task_done()
                break
            else:
                print("[%d/%d] @%s, <%s> draw (%d, %d), status: %d, "
                      "retry after %ds, cost %.2fs"
                      % (index, total, datetime.now(), user_id, x, y,
                          status['code'], wait_time, cost_time))
                time.sleep(wait_time)

        # sleep for cool-down interval
        time_span = 10
        if wait_time > time_span:
            time.sleep(wait_time - time_span)
            start_time = time.time()
            ret = up.lazy_update_image()
            end_time = time.time()
            if ret == -1:
                print("<%s> update image in %.2fs" %
                      (user_id, end_time - start_time))
            else:
                print("<%s> lazily updated %.2fs before" %
                      (user_id, end_time - ret))

            if end_time - start_time < time_span:
                time.sleep(time_span - (end_time - start_time))
        elif wait_time > 0:
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

    total_task = len(tasks)
    task_queue = Queue.Queue()
    up = UpdateImage()
    up.update_image()
    for index, task in enumerate(tasks, 1):
        task_queue.put((index, task))

    thread_list = []
    count = 1
    with open(user_filename, "r") as fp:
        for user_cmd in fp:
            # Skip empty line
            user_cmd = user_cmd.strip()
            if not user_cmd:
                continue

            user_id = "User-%d" % count
            count += 1
            thread = threading.Thread(
                target=thread_main,
                args=(user_id, user_cmd, task_queue, total_task, up))
            thread.daemon = True
            thread.start()
            thread_list.append(thread)

    # keep responsiveness
#     for thread in thread_list:
#         while True:
#             try:
#                 if not thread.is_alive():
#                     break
#                 thread.join(1)
#             except KeyboardInterrupt:
#                 print("Ctrl-c pressed, exiting")
#                 sys.exit()
    while True:
        try:
            time.sleep(1)
            if task_queue.empty():
                print("Finished all tasks, existing")
                sys.exit()
        except KeyboardInterrupt:
            print("Ctrl-c pressed, exiting")
            sys.exit()

    print("Exiting")
