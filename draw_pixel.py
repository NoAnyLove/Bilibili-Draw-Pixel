import time
import json
from datetime import datetime
import sys
import Queue
import threading
from update_image import UpdateImage
from util import rgb_to_hex, process_tasks, \
    draw_pixel_with_requests, extract_cookies, process_status_101


def thread_main(user_id, user_cmd, task_queue, total, up,
                use_incremental_update):

    time.sleep(3)

    # used to count the number of occurrence of code -101
    invalid_cookie_counter = 0

    print("%s start working" % user_id)
    # cmd_template = process_cmd_template(user_cmd)
    user_cookies = extract_cookies(user_cmd)
    wait_time = -1
    while True:
        index, (x, y, color) = task_queue.get()

        while True:

            # check if it is already the correct color
            cur_rgb = up.get_image_pixel_sync(x, y)
            cur_rgb_hex = rgb_to_hex(*cur_rgb)
            wait_time = -1
            if cur_rgb_hex == color:
                print("[%d/%d] @%s, <%s> skip correct pixel (%d, %d)" %
                      (index, total, datetime.now(), user_id, x, y))
                break

            # output may be an empty string
            print("<%s> start to draw (%d, %d)" % (user_id, x, y))

            status_code, wait_time, cost_time = draw_pixel_with_requests(
                user_cookies, x, y, color)

            if status_code == 0:
                print("[%d/%d] @%s, <%s> draw (%d, %d) with %s, status: %d,"
                      " cost %.2fs" %
                      (index, total, datetime.now(), user_id,
                       x, y, color, status_code, cost_time))
#             elif status_code == -400:   # not ready to draw a new pixel
#                 print("[%d/%d] @%s, <%s> draw (%d, %d), status: %d, "
#                       "retry after %ds, cost %.2fs"
#                       % (index, total, datetime.now(), user_id, x, y,
#                           status_code, wait_time, cost_time))
            elif status_code == -101:
                process_status_101(invalid_cookie_counter,
                                   user_id, cost_time, user_cookies)
            else:
                print("[%d/%d] @%s, <%s> draw (%d, %d), status: %s, "
                      "retry after %ds, cost %.2fs"
                      % (index, total, datetime.now(), user_id, x, y,
                          status_code, wait_time, cost_time))

            # sleep for cool-down time
            if wait_time > 0:
                time.sleep(wait_time)

                if not use_incremental_update:
                    # update image in case it wait for too long
                    up.lazy_update_image()


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
    process_tasks(tasks)

    total_task = len(tasks)
    task_queue = Queue.Queue()

    # TODO: flag
    use_incremental_update = True
    up = UpdateImage()
    if use_incremental_update:
        up.update_image_with_incremental_update()
    else:
        # this is necessary, because we only call lazy_update_image at the end
        # of loop inside worker thread
        up.update_image()

    for index, task in enumerate(tasks, 1):
        task_queue.put((index, task))

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
                args=(user_id, user_cmd, task_queue, total_task, up,
                      use_incremental_update))
            thread.daemon = True
            thread.start()
            thread_list.append(thread)

    print('[INFO] loaded %d accounts' % (count - 1))

    while True:
        try:
            time.sleep(1)
            if task_queue.empty():
                print("Finished all tasks, existing")
                sys.exit()
        except KeyboardInterrupt:
            print("Ctrl-c pressed, exiting")
            sys.exit()
