#! -*-encoding: utf-8 -*-
"""
    博文总结、视频总结，是在预计算的时候 , 算出来这个博文下功能引导有博文总结、视频总结的情况下，才会计算博文总结、视频总结；
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
REDIS_KEY_PREFIX = "blog_pre_cache"

_client = RedisClusterClient(
    hosts=HOSTS,
    ports=PORTS,
    socket_timeout=100,
)


async def get_blog_video_summary(mid: str = "", postfix: str = "blog_summary", log=None) -> dict:
    """
        根据 mid 从 Redis 中获取博文/视频总结内容
    """
    mid_key = f"{REDIS_KEY_PREFIX}:{mid}:{postfix}"
    res_json = await _client.get(prefix="",key=mid_key, log=log)
    if not res_json:
        return {}
    return {
        "mid": mid,
        "summary": res_json,
    }


if __name__ == "__main__":
    """
    5327439330023557 : blog_summary
    5327486122721506 : video_summary
    """
    res = asyncio.run(
        get_blog_video_summary(mid="5327486122721506", postfix="video_summary")
    )
    print(res)