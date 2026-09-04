import asyncio
import re
from urllib.parse import urlunparse, urlparse
import aiohttp


class MidConverter:
    _string = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    _encode_block_size = 7
    _decode_block_size = 4

    @classmethod
    def multi_from10to62(cls, mids):
        """批量从10进制转换到62进制"""
        return {mid: cls.from10to62(str(mid)) for mid in mids}

    @classmethod
    def multi_from62to10(cls, mids, compat=False, for_mid=True):
        """批量从62进制转换到10进制"""
        return {mid: cls.from62to10(str(mid), compat, for_mid) for mid in mids}

    @classmethod
    def from10to62(cls, mid):
        """将10进制mid转换为62进制"""
        mid = str(mid)
        result = ""
        mid_len = len(mid)
        segments = -(-mid_len // cls._encode_block_size)  # ceil除法
        start = mid_len
        for _ in range(1, segments):
            start -= cls._encode_block_size
            seg = mid[start:start + cls._encode_block_size]
            seg = cls._encode_segment(int(seg))
            result = seg.zfill(cls._decode_block_size) + result
        result = cls._encode_segment(int(mid[0:start])) + result
        return result

    @classmethod
    def from62to10(cls, s, compat=False, for_mid=True):
        """将62进制mid转换为10进制"""
        s = str(s)
        mid = ""
        s_len = len(s)
        segments = -(-s_len // cls._decode_block_size)
        start = s_len
        for _ in range(1, segments):
            start -= cls._decode_block_size
            seg = s[start:start + cls._decode_block_size]
            seg = cls._decode_segment(seg)
            mid = seg.zfill(cls._encode_block_size) + mid
        mid = cls._decode_segment(s[0:start]) + mid

        if for_mid:
            mid_len = len(mid)
            first = mid[0]
            if mid_len == 16 and first in ['3', '4']:
                return mid
            if mid_len == 19 and first == '5':
                return mid

        if compat and mid[:3] not in ['109', '110', '201', '211', '221', '231', '241']:
            mid = cls._decode_segment(s[0:4]) + cls._decode_segment(s[4:])

        if for_mid:
            if mid[0] == '1' and len(mid) > 8 and mid[7] == '0':
                mid = mid[:7] + mid[8:]
        return mid

    @classmethod
    def _encode_segment(cls, num):
        """10进制转62进制"""
        if num == 0:
            return '0'
        out = ''
        while num > 0:
            idx = num % 62
            out = cls._string[idx] + out
            num //= 62
        return out

    @classmethod
    def _decode_segment(cls, s):
        """62进制转10进制"""
        out = 0
        base = 1
        for char in reversed(s):
            out += base * cls._string.index(char)
            base *= 62
        return str(out)

    @classmethod
    def is_weibo_url(cls, s: str) -> str:
        """判断是否为微博URL并提取mid"""
        # 匹配完整的微博URL结构，确保格式正确
        pattern = r"https?://(?:www\.|m\.)?weibo\.(?:com|cn)/(?:status|detail|[0-9]{6,11})/([a-zA-Z0-9]+)"
        match = re.search(pattern, s, re.IGNORECASE)
        if match and match.group(1):
            # 检查提取的mid是否为纯数字
            if re.match(r"^\d+$", match.group(1)):
                return match.group(1)
        return ''

    @classmethod
    def is_weibo_mid(cls, s: str, send_from="") -> str:
        """判断是否为微博mid（16位数字）"""
        if re.match(r"^\d{16}$", s) and send_from != "level_two_comment":
            return s
        return ''

    @classmethod
    def is_short_url(cls, s: str) -> bool:
        """判断是否为短链接 (t.cn)"""
        return s.startswith(('http://t.cn/', 'https://t.cn/'))

    @classmethod
    async def get_long_url(cls, short_url):
        url = "http://i2.api.weibo.com/2/short_url/expand.json?source=2936099636&url_short={}".format(short_url)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                async with session.get(url=url) as r:
                    if r.status == 200:
                        res = await r.json()
                        url_long = res['urls'][0]['url_long']
                        return url_long
        except:
            return ""

    @classmethod
    async def judge_is_mid(cls, url):
        mid_id = ""
        if MidConverter.is_short_url(url):
            long_url = await MidConverter.get_long_url(url)
            if long_url:
                url = long_url
        clean_url = urlunparse(urlparse(url)._replace(query=""))  # 清除 query 部分
        # 正则匹配，兼容多种路径形式
        pattern = re.compile(r"^https?://([^/]+\.)?weibo\.(com|cn)/(\d+)/([A-Za-z0-9]+)")
        match = pattern.search(clean_url)
        if match:
            wb_user_id = match.group(3)
            weibo_id = match.group(4)
            # 如果 ID 是纯数字，不转换
            if weibo_id.isdigit():
                mid_id = MidConverter.is_weibo_url(url)
                return mid_id
            # 否则转成长 ID
            mid_id = MidConverter.from62to10(weibo_id)
            clean_url = f"https://weibo.com/{wb_user_id}/{mid_id}"
        return mid_id


    @classmethod
    def is_url(cls, input_str: str) -> bool:
        """判断是否包含URL"""
        return re.search(r"(http|https)://", input_str) is not None

    @classmethod
    async def query_get_uid(cls, query, send_from=""):
        try:
            if MidConverter.is_weibo_mid(query, send_from):
                return query

            if MidConverter.is_url(query):
                mid = await MidConverter.judge_is_mid(query)
                if mid:
                    return mid
        except Exception as e:
            pass

        return ""


async def main():

    url = await MidConverter.query_get_uid('https://weibo.com/1904098061/QuO8LjBAI')
    print(url)
    url = await MidConverter.query_get_uid('http://t.cn/AXfVXujB')
    print(url)
    url =await MidConverter.query_get_uid('https://weibo.com/1904098061/5273425834672736')
    print(url)
    url = await MidConverter.query_get_uid('http://t.cn/AXVAUcYG')
    print(url)
    url = await MidConverter.query_get_uid('5273425834672736')
    print(url)
    url = await MidConverter.query_get_uid('百度')
    print(url)


if __name__ == '__main__':

    asyncio.run(main())