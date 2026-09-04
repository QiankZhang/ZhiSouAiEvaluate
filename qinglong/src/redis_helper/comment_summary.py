#! -*-encoding: utf-8 -*-
"""
    评论总结: 评论数大于300
"""

import asyncio
from src.redis_helper.base import RedisClusterClient


HOSTS = [
    "pkm27034.eos.grid.sina.com.cn", "pkm27035.eos.grid.sina.com.cn",
    "pkm27036.eos.grid.sina.com.cn", "pkm27037.eos.grid.sina.com.cn",
    "pkm27038.eos.grid.sina.com.cn", "pkm27039.eos.grid.sina.com.cn",
    "pkm27040.eos.grid.sina.com.cn", "pkm27041.eos.grid.sina.com.cn",
    "pkm27042.eos.grid.sina.com.cn", "pkm27043.eos.grid.sina.com.cn",
    "pkm27044.eos.grid.sina.com.cn", "pkm27045.eos.grid.sina.com.cn",
    "pkm27046.eos.grid.sina.com.cn", "pkm27047.eos.grid.sina.com.cn",
    "pkm27048.eos.grid.sina.com.cn", "pkm27049.eos.grid.sina.com.cn",
    "pkm27050.eos.grid.sina.com.cn", "pkm27051.eos.grid.sina.com.cn",
    "pkm27052.eos.grid.sina.com.cn", "pkm27053.eos.grid.sina.com.cn",
    "pkm27054.eos.grid.sina.com.cn", "pkm27055.eos.grid.sina.com.cn",
    "pkm27056.eos.grid.sina.com.cn", "pkm27057.eos.grid.sina.com.cn",
    "pkm27058.eos.grid.sina.com.cn", "pkm27059.eos.grid.sina.com.cn",
    "pkm27060.eos.grid.sina.com.cn", "pkm27061.eos.grid.sina.com.cn",
    "pkm27062.eos.grid.sina.com.cn", "pkm27063.eos.grid.sina.com.cn",
    "pkm27064.eos.grid.sina.com.cn", "pkm27065.eos.grid.sina.com.cn",
]
PORTS = list(range(27034, 27066))
REDIS_KEY_PREFIX = "wis_blog_summary"

_client = RedisClusterClient(
    hosts=HOSTS,
    ports=PORTS,
    socket_timeout=100,
)


async def get_comment_summary(mid: str, log=None) -> dict:
    """
        根据 mid 从 Redis 中获取评论总结内容
    """
    mid_key = f"{REDIS_KEY_PREFIX}:{mid}"
    res_json = await _client.get(prefix="",key=mid_key, log=log)
    if not res_json:
        return {}
    return {
        "mid": mid,
        "summary": res_json,
    }


if __name__ == "__main__":
    """
    5327799166705700
    5327909961076451
    """
    res = asyncio.run(get_comment_summary(mid="5327909961076451"))
    print(res)
