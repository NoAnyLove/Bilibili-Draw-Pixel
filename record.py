import time
from datetime import datetime
from update_image import UpdateImage

interval = 180


def log():
    print("@%s record current image" % datetime.now())


if __name__ == "__main__":
    up = UpdateImage(True)
    print("Start @%s" % datetime.now())
    log()
    up.update_image()
    while True:
        time.sleep(interval)
        log()
        up.update_image()
