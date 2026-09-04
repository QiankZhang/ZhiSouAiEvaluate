#! -*-encoding: utf-8 -*-

import json
import hashlib

import redis.asyncio as aioredis


class RedisClusterClient:
    """Redis 集群客户端基类，封装一致性哈希分片和通用查询逻辑"""

    def __init__(
        self,
        hosts: list[str],
        ports: list[int],
        socket_timeout: int = 3,
    ):
        """
        Args:
            hosts: Redis 服务器主机列表
            ports: Redis 服务器端口列表
            socket_timeout: 连接超时时间（秒）
        """
        if len(hosts) != len(ports):
            raise ValueError("hosts 和 ports 长度必须一致")
        self.hosts = hosts
        self.ports = ports
        self.socket_timeout = socket_timeout

    def get_hash_index(self, key: str) -> int:
        """根据 key hash 计算应该使用哪个 Redis 服务器"""
        md5 = hashlib.md5()
        md5.update(key.encode(encoding="utf-8"))
        m = md5.hexdigest()
        map_key = str(m)[-2:]
        return int(map_key, 16) % len(self.ports)

    def get_redis_server(self, key: str = "") -> aioredis.Redis:
        """根据 key 获取对应的 Redis 服务器连接"""
        index = self.get_hash_index(key=key)
        return aioredis.Redis(
            host=self.hosts[index],
            port=self.ports[index],
            socket_timeout=self.socket_timeout,
            health_check_interval=1,
            decode_responses=True,
        )

    async def get(self, prefix:str="", key: str="", log=None) -> dict | None:
        """根据 key 从 Redis 中获取并解析 JSON 数据

        Args:
            key: 完整的 Redis key
            log: 可选的日志对象

        Returns:
            解析后的 dict，如果 key 不存在则返回 None
        """
        if prefix:
            redis_cli = self.get_redis_server(key=prefix)
        else:
            redis_cli = self.get_redis_server(key=key)
            
        if log:
            log.info(f"key: {key}")
        try:
            raw = await redis_cli.get(key)
            if not raw:
                return None
            return json.loads(raw)
        finally:
            await redis_cli.aclose()