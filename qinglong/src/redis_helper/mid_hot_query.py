#! -*-encoding: utf-8 -*-
"""
    根据 mid 从 Redis 中查询是否为热搜博文及热搜 query
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

REDIS_KEY_PREFIX = "resou_mid_list_0707"

_client = RedisClusterClient(
    hosts=HOSTS,
    ports=PORTS,
    socket_timeout=100,
)


async def get_mid_hot_query(prefix:str="", mid: str = "", log=None) -> dict:
    """
        根据 mid 从 Redis 中查询是否为热搜博文及热搜 query
    """
    mid_key = f"{REDIS_KEY_PREFIX}:mid_query:{mid}"
    res_json = await _client.get(prefix=prefix, key=mid_key, log=log)
    if not res_json:
        return {}
    return {
        "mid": mid,
        "queries": res_json,
    }


if __name__ == "__main__":
    """
    5328452447110692\t热搜
    """
    mid = "5272383340413162"
    res = asyncio.run(get_mid_hot_query(mid=mid))
    print(res)
