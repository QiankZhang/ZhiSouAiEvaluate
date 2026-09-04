#! -*- encoding: utf-8 -*-

import os
import re
import aiohttp
import asyncio
import requests
from typing import List, Dict, Optional, Callable, Any
from tqdm.asyncio import tqdm_asyncio


class BaseTask():

    def __init__(self, logger=None):
        self.log = logger

    async def batch_async_exec(
        self,
        async_func: Callable,
        task_args_list: List[tuple],
        semaphore: asyncio.Semaphore = None,
        show_progress: bool = False,
    ) -> List[Any]:
        """
        通用批量并发执行器
            async_func: 异步函数（支持任意参数）
            task_args_list: 任务参数列表
            semaphore: 并发信号量
            show_progress: 是否显示进度条
        """
        async def safe_process(args):
            if semaphore:
                async with semaphore:
                    return await async_func(*args)
            else:
                return await async_func(*args)

        tasks = [safe_process(args) for args in task_args_list]

        if show_progress:
            results = await tqdm_asyncio.gather(*tasks, desc="处理中", unit="条")
        else:
            results = await asyncio.gather(*tasks)

        return results