import asyncio
import hashlib
import json

import redis.asyncio as aioredis

'''
博文场景入口进入的用户行为数据
'''

EXPIRE_SECONDS = 180 * 24 * 3600  # 180 天

# PKM_HOSTS = [f"pkm{port}.eos.grid.sina.com.cn" for port in range(26178, 26186)]
PKM_HOSTS = [f"pks{port}.hebe.grid.sina.com.cn" for port in range(26178, 26186)]

PKM_PORTS = list(range(26178, 26186))

_pkm_clients = [
    aioredis.Redis(
        host=host, port=port, db=0,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        protocol=2,
    )
    for host, port in zip(PKM_HOSTS, PKM_PORTS)
]


def _get_client(key: str):
    m = hashlib.md5()
    m.update(key.encode("utf-8"))
    idx = int(m.hexdigest()[-2:], 16) % len(_pkm_clients)
    return _pkm_clients[idx]


async def get_data(query: str):
    md5_hash = hashlib.md5(query.encode("utf-8")).hexdigest()
    key = f"follow_up_query_{md5_hash}"
    client = _get_client(key)
    return await client.lrange(key, 0, -1)


async def delete_key(query: str):
    md5_hash = hashlib.md5(query.encode("utf-8")).hexdigest()
    key = f"follow_up_query_{md5_hash}"
    client = _get_client(key)
    await client.delete(key)


async def get_statis_data(query: str):
    md5_hash = hashlib.md5(query.encode("utf-8")).hexdigest()
    key = f"follow_up_query_statis_{md5_hash}"
    client = _get_client(key)
    value = await client.get(key)
    if value is None:
        return None
    return json.loads(value)

async def main(mid:str=""):
    """
    """
    result = await get_statis_data(mid)
    print(result)
    # with open('/data1/minisearch/guoliang21/easy_ask/data/a.txt','r') as reader:
    #     for line in reader:
    #         # import pdb;pdb.set_trace()
    #         mid = line.strip()
    #         result = await get_statis_data(mid)
    #         print(result)

if __name__ == "__main__":
    # query = "5321245399712533"
    # asyncio.run(delete_key(query))
    # print(asyncio.run(get_data(query)))
    asyncio.run(main(mid="5321245399712533"))