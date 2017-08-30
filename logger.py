import logging
import sys

PREFIX = "BDraw"

LEVEL = logging.INFO

formatter = logging.Formatter(
    '%(asctime)s, %(levelname)s-%(name)s: %(message)s')

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(LEVEL)
handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(LEVEL)
root_logger.addHandler(handler)


def set_logger_level(level=logging.DEBUG):
    logging.getLogger().setLevel(level)


def get_logger(name):
    logger = logging.getLogger("%s.%s" % (PREFIX, name))
    return logger
