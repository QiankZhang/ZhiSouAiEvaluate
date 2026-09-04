# -*- encoding: utf-8 -*-
"""
    博文总结、视频总结，是在预计算的时候 , 算出来这个博文下功能引导有博文总结、视频总结的情况下，才会计算博文总结、视频总结；
"""

import asyncio
from src.redis_helper.base import RedisClusterClient

import json
import redis
from datetime import datetime

HOSTS = ["rm51798.eos.grid.sina.com.cn"]
PORTS = [51798]

REDIS_KEY_PREFIX = "blog_pre_cache"

_client = RedisClusterClient(
    hosts=HOSTS,
    ports=PORTS,
    socket_timeout=100,
)


async def get_user_behaviour(mid: str = "", log=None) -> dict:
    """
        根据 mid 从 Redis 中获取博文/视频总结内容
    """
    mid_key = f"mid:q1:{mid}"
    res_json = await _client.get(prefix="",key=mid_key, log=log)
    if not res_json:
        return {}
    # {'mid': '5331605792754520', 'summary': {'questions': ['密室大逃脱在哪个平台播出？#2', '密室大逃脱亮点#1'], 'function': ['影视识别', '最新进展', '剧情解读'], 'update_time': '2026-09-02 15:58:54'}}
    questions = res_json.get('questions', [])
    follow_queries = []
    for item in questions:
        item = item.strip().split('#')
        follow_queries.append({'next_query': item[0], 'count': int(item[1])})
    return {
        "mid": mid,
        "follow_queries": follow_queries
    }


if __name__ == "__main__":
    """
    5327439330023557 : blog_summary
    5327486122721506 : video_summary
    """
    res = asyncio.run(
        get_user_behaviour(mid="5331605792754520")
    )
    print(res)