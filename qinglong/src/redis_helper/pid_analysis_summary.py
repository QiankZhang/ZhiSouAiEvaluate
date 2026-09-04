#! -*-encoding: utf-8 -*-

"""
    根据 pid 从 Redis 中获取图片搜索分析结果; 同时也可以选择使用custom_data_api中的请求;
"""

import asyncio
from src.redis_helper.base import RedisClusterClient


HOSTS = [
    "pkm26770.eos.grid.sina.com.cn", "pkm26771.eos.grid.sina.com.cn",
    "pkm26772.eos.grid.sina.com.cn", "pkm26773.eos.grid.sina.com.cn",
    "pkm26774.eos.grid.sina.com.cn", "pkm26775.eos.grid.sina.com.cn",
    "pkm26776.eos.grid.sina.com.cn", "pkm26777.eos.grid.sina.com.cn",
]

PORTS = list(range(26770, 26778))
REDIS_KEY_PREFIX = "image_search_result"

_client = RedisClusterClient(
    hosts=HOSTS,
    ports=PORTS,
    socket_timeout=100,
)


async def get_pid_analysis_summary(pid: str, log=None) -> dict:
    """
        根据 pid 从 Redis 中获取图片搜索分析结果
    """
    mid_key = f"{REDIS_KEY_PREFIX}:{pid}"
    res_json = await _client.get(prefix="",key=mid_key, log=log)
    if not res_json:
        return {}
    return {
        "mid": pid,
        "pid_analysis": res_json,
    }


if __name__ == "__main__":
    """
    006IWOihgy1if9ug2wypqj30wr1z0kc5
    """
    pid = "006IWOihgy1if9ug2wypqj30wr1z0kc5"
    res = asyncio.run(get_pid_analysis_summary(pid=pid))
    print(res)
