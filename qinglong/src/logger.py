#！ -*- encoding:utf-8 -*-

import os
import logging
from logging.handlers import RotatingFileHandler


# 【关键】屏蔽所有第三方库日志，只保留自己的
logging.getLogger("qdrant_client").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


def get_logger(log_path: str = "./logs", date_info:str=""):
    """
    """
    log_dir = f"{log_path}/{date_info}"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 1. 创建根日志器
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    # 2. 日志格式
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(funcName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    info_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, "info.txt"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5, 
        encoding="utf-8"
    )
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(formatter)
    info_handler.addFilter(lambda record: record.levelno < logging.ERROR)

    error_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, "error.txt"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    logger.addHandler(info_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)

    return logger


if __name__=="__main__":
    """
    """
    log = get_logger(log_path= "./logs", date_info="20260422")
    log.info("aaa")
    log.error("bbb")