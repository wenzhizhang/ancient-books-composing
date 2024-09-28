import logging
import os

log_path = 'log'
if not os.path.exists(log_path):
    os.makedirs(log_path)

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"


def formatter_message(message, use_color):
    if use_color:
        message = message.replace("$RESET", RESET_SEQ).replace("$BOLD", BOLD_SEQ)
    else:
        message = message.replace("$RESET", "").replace("$BOLD", "")
    return message


COLORS = {
    'WARNING': YELLOW,
    'INFO': WHITE,
    'DEBUG': BLUE,
    'CRITICAL': YELLOW,
    'ERROR': RED
}


class ColoredFormatter(logging.Formatter):
    def __init__(self, msg, use_color=True):
        logging.Formatter.__init__(self, msg)
        self.use_color = use_color

    def format(self, record):
        levelname = record.levelname
        if self.use_color and levelname in COLORS:
            levelname_color = COLOR_SEQ % (30 + COLORS[levelname]) + levelname + RESET_SEQ
            record.levelname = levelname_color
        return logging.Formatter.format(self, record)


# Custom logger class with multiple destinations
class ColoredLogger(logging.Logger):
    FORMAT = "%(asctime)s | %(filename)s | Line: %(lineno)-3d | $BOLD%(levelname)s$RESET | %(message)s"
    COLOR_FORMAT = formatter_message(FORMAT, True)

    def __init__(self, name):
        logging.Logger.__init__(self, name, logging.DEBUG)

        color_formatter = ColoredFormatter(self.COLOR_FORMAT)
        default_formatter = logging.Formatter(
            '%(asctime)s | %(filename)s | Line: %(lineno)-3d | %(levelname)s | %(message)s')
        separator = os.sep
        fh = logging.FileHandler('{}info.log'.format(log_path + separator))
        fh1 = logging.FileHandler('{}error.log'.format(log_path + separator))
        fh2 = logging.FileHandler("{}debug.log".format(log_path + separator))
        fh.setLevel(logging.INFO)
        fh1.setLevel(logging.ERROR)
        fh2.setLevel(logging.DEBUG)

        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)

        fh.setFormatter(default_formatter)
        fh1.setFormatter(default_formatter)
        fh2.setFormatter(default_formatter)
        ch.setFormatter(color_formatter)

        self.addHandler(fh)
        self.addHandler(fh1)
        self.addHandler(fh2)
        self.addHandler(ch)


class Logger(ColoredLogger):
    def __init__(self, name):
        ColoredLogger.__init__(self, name)
        # logger = logging.getLogger(name)
        # logger.setLevel(logging.DEBUG)
        # return logger

    @staticmethod
    def get_error_message(error):
        if hasattr(error, 'error_message'):
            error_message = error.error_message
        else:
            error_message = error
        return error_message
