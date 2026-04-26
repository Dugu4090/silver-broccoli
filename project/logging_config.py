import logging
import os
import sys


def setup_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)
    return logging.getLogger("studymate")


log = setup_logging()
