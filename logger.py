import logging
import os
from logging.handlers import RotatingFileHandler

# path of log file
LOG_FILE = './logs.log'

def get_logger(name=__name__):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG) 

    if not logger.hasHandlers():

        # Logs format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # handler for show logs in console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # handler for delete logs more than 20MB
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=20*1024*1024, backupCount=0, encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


logger = get_logger('dev_logger')