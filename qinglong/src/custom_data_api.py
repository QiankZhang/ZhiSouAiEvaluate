#! -*- encoding:utf-8 -*-

import re
import time
import json
import requests
import aiohttp
import asyncio
from urllib.parse import quote

from src.redis_helper.mid_hot_query import get_mid_hot_query
from src.utils import delete_wbcustomblock, remove_media_block


async def request_post_api(url: str = "", payload: dict = {}, log=None, max_retries: int = 5) -> dict:
    """
        内容数据接口，重试机制
    """
    timeout = aiohttp.ClientTimeout(total=1000)
    async with aiohttp.ClientSession(timeout=timeout) as session: 
        for attempt in range(1, max_retries + 1):
            try:
                async with session.post(url, json=payload) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            except asyncio.TimeoutError:
                if log: log.warning(f"请求超时, 第 {attempt} 次, url={url}")
            except aiohttp.ClientError as e:
                if log: log.warning(f"请求失败, 第 {attempt} 次, url={url}")
            except Exception as e:
                if log: log.warning(f"未知错误, 第 {attempt} 次, url={url}")

            if attempt < max_retries:
                await asyncio.sleep(2)

    if log: 
        log.error(f"重试 {max_retries} 次后仍失败, url={url}", exc_info=True)
    return {}


async def request_get_api(url: str = "", params: dict = None, max_retries:int=5, log=None) -> dict:
    """
        内容数据接口，重试机制
    """
    timeout=aiohttp.ClientTimeout(total=1000)
    async with aiohttp.ClientSession(timeout=timeout) as session: 
        for attempt in range(1, max_retries + 1):
            try:
                async with session.get(url, params=params) as resp:
                    resp.raise_for_status()
                    text = await resp.text()
                    res = json.loads(text)
                    return res
            except asyncio.TimeoutError:
                if log: log.warning(f"请求超时, 第 {attempt} 次, url={url}")
            except aiohttp.ClientError as e:
                if log: log.warning(f"请求失败, 第 {attempt} 次, url={url}")
            except Exception as e:
                if log: log.warning(f"未知错误, 第 {attempt} 次, url={url}")

            if attempt < max_retries:
                await asyncio.sleep(2)

    if log: 
        log.error(f"重试 {max_retries} 次后仍失败, url={url}", exc_info=True)
    return {}


async def weibo_search_async(query:str="", log=None):
    """
        获取微博物料
    """
    url = 'http://10.54.45.97:30123/api/material/latest'
    payload = {
        "query": query,
        "need_return_keys": [
            "query",
            "ds_struct_material",
            "link_list",
            "link_type_list"
        ]
    }

    try:
        material_dict = await request_post_api(url=url, payload=payload, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict\tquery:{query}", exc_info=True)
        material_dict = {}

    return material_dict


async def get_ocr_voice_info(mid: str = "", log=None) -> dict:
    """
        基于mid, 获取博文中图片OCR和视频中的音转文,后面不用了,从hbase中拿VIDEO_VOICE和IDX_OCR_TEXT
    """
    url = "http://10.54.45.97:30123/api/material/mid"
    payload = {
        "query": mid,
        "skill_name": "guoliang_0716",
        "need_return_keys": ["mid_ocr", "mid_voice"]
    }

    try:
        material_dict = await request_post_api(url=url, payload=payload, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict\tmid:{mid}", exc_info=True)
        material_dict = {}

    return material_dict


async def get_tag_m3_blog(query: str = "", log=None) -> dict:
    """
        根据query, 搜索博文, 返回top10; 每个返回结果给出对应的mid、相关性分数、质量分数、发博者类型
    """
    url = "http://10.54.45.97:30123/api/material/latest"
    payload = {
        "query": query,
        "skill_name": "zhuiwen_u_0616",
        "need_return_keys": ["struct_content_list", "raw_material_list"]
    }
    try:
        material_dict = await request_post_api(url=url, payload=payload, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict\tquery:{query}", exc_info=True)
        material_dict = {}

    return material_dict


async def search_related_blog_by_query(query: str = "", log=None) -> dict:
    """
        根据query, 搜索相似博文
    """
    url = "http://10.54.45.97:30123/api/material/latest"
    payload = {
        "query": query,
        "skill_name": "zhuiwen_u_0616",
        "need_return_keys": ["struct_content_list", "raw_material_list"]
    }
    try:
        material_dict = await request_post_api(url=url, payload=payload, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict\tquery:{query}", exc_info=True)
        material_dict = {}

    return material_dict


async def search_related_blog_by_mid(mid: str = "", log=None) -> dict:
    """
        基于mid, 搜索相似博文
    """
    url = "http://10.54.45.97:30123/api/material/mid"
    payload = {
        "query": mid,
        "skill_name": "zhuiwen_mid_top10",
        "llm_name": "deepseek_verification",
        "need_return_keys": ["ds_struct_material", "raw_material_list", "link_list"]
    }
    try:
        material_dict = await request_post_api(url=url, payload=payload, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict\mid:{mid}", exc_info=True)
        material_dict = {}

    return material_dict



async def get_hbase(mid: str = "", log=None) -> dict:
    """
        调用Hbase接口
    """
    # 线上
    url = f"http://getdata.search.weibo.com/getdata/querydata.php?condition={mid}&mode=weibo&format=json"
    # 离线 宏中
    # url = "http://getdata.search.weibo.com/getdata/querydata2.php?condition=%s&mode=weibo&format=json&hbase=1" % (mid)
    try:
        material_dict = await request_get_api(url=url, params={}, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict\tmid:{mid}", exc_info=True)
        material_dict = {}

    return material_dict


async def search_people_zhisou(query: str = "", log=None) -> dict:
    """
        人物智搜结果
    """
    url = "http://admin.ai.s.weibo.com/api/llm/search_all.json"
    payload = {"q": query}
    
    try:
        material_dict = await request_post_api(url=url, payload=payload, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict\tquery:{query}", exc_info=True)
        material_dict = {}

    return material_dict


async def search_people(query: str = "", page_size:int=10, log=None) -> dict:
    """
        博主个人主页博文
    """
    url = (
        f"http://i.search.weibo.com/search/wis/user.json"
        f"?mblog_screen_name={quote(query)}&page_size={page_size}"
    )

    try:
        material_dict = await request_get_api(url=url, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict\tmid:{mid}", exc_info=True)
        material_dict = {}

    return material_dict


async def get_hot_query(log=None) -> dict:
    """
        在榜热搜 query
    """
    url = "http://miniblog.search.weibo.com/topsearch/get_hot_words.php"

    try:
        material_dict = await request_get_api(url=url, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict", exc_info=True)
        material_dict = {}

    return material_dict


async def get_hot_word_summary(querystr: str, sidstr: str = "search_arch",log=None) -> dict:
    """
        获取热搜词总结
    """
    url = "http://admin.ai.s.weibo.com/api/wis/show.json"
    params = {
        "querystr": querystr,
        "sidstr": sidstr,
    }
    # print(url)
    try:
        material_dict = await request_get_api(url=url, params=params, log=log)
        # print(material_dict)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict:{querystr}", exc_info=True)
        material_dict = {}

    return material_dict


async def build_pid_analysis_task(pid: str, log=None) -> dict:
    """
        把pid推到队列里, 配合get_pid_analysis_summary一起使用
    """
    url = "http://admin.ai.s.weibo.com/api/llm/analysis_once_queue.json"
    params = {
        "query": pid,
        "models": "picture",
        "source": "121",
        "sid": "zs_picture_api"
    }

    try:
        material_dict = await request_get_api(url=url, params=params, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict:{pid}", exc_info=True)
        material_dict = {}

    return material_dict


async def get_pid_analysis_summary(pid: str, desc:str="", sidstr: str = "zs_picture_api",log=None) -> dict:
    """
        获取图片分析结果, 需要先执行build_pid_analysis_task, 把pid推到队列里,刘昊提供
    """
    url = "http://wisservices.search.weibo.com/api/v1/task/query"
    params = {
        "pid": pid,
        "sid": sidstr,
    }

    try:
        material_dict = await request_get_api(url=url, params=params, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict:{pid}", exc_info=True)
        material_dict = {}

    material_dict['desc'] = desc

    return material_dict


async def get_pid_analysis_summary_v2(pid: str, log=None) -> dict:
    """
        根据pid获取图片分析结果, 丽婷提供
    """
    url = "http://admin.ai.s.weibo.com/api/wis/show.json"
    params = {
        "query": pid,
        "content_type": "loop",
        "cot": '14',
        "echo_ori_q_attr": '1',
        "sid": 'pusou_picture_2',
    }

    try:
        material_dict = await request_get_api(url=url, params=params, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict:{pid}", exc_info=True)
        material_dict = {}

    return material_dict


async def get_hot_search_material(query: str, log=None) -> dict:
    """
        热搜物料接口
    """
    url = "http://zsbd.api.search.weibo.com:30123/api/material/latest"
    payload = {
        "query": query,
        "need_return_keys": ["content", "ds_struct_material"]
    }

    try:
        material_dict = await request_post_api(url=url, payload=payload, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict\tquery:{query}", exc_info=True)
        material_dict = {}

    return material_dict


async def get_none_hot_search_material(query: str, log=None) -> dict:
    """
        非热搜物料接口, 返回top10
    """
    url = "http://zsbd.api.search.weibo.com:30123/api/material/latest"
    payload = {
        "query": query,
        "prompt_scene": "unify_only_0702",
        "need_return_keys": ["ds_struct_material", "link_type_list"]
    }

    try:
        material_dict = await request_post_api(url=url, payload=payload, log=log)
        
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict\tquery:{query}", exc_info=True)
        material_dict = {}

    return material_dict


async def fetch_zhisou_ret(query:str="", log=None) -> str:
    """
        获取智搜结果
    """
    url = f"http://admin.ai.s.weibo.com/api/llm/analysis_once_res.json?query={query}"
    try:
        material_dict = await request_get_api(url=url, log=log)
        r_deepseek = material_dict['data']['deepseek']['content']
        rrr = remove_media_block(r_deepseek)
        rrr = re.sub(r'<think>.*?</think>', '', rrr, flags=re.DOTALL)
        return rrr
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict:{query}", exc_info=True)
            
    return ""

async def get_1_n_response(query: str, log=None) -> dict:
    """
        获取1+n的结果,1是智搜结果,这里只拿n的结果
    """
    url = "http://admin.ai.s.weibo.com/api/llm/analysis_once_res.json"
    params = {
        "query": query
    }

    try:
        material_dict = await request_get_api(url=url, params=params, log=log)
    except Exception as e:
        if log:
            log.error(f"request custom api error, return empty dict:{pid}", exc_info=True)
        material_dict = {}
    return material_dict


if __name__ == "__main__":
    """
    """
    print(asyncio.run(get_1_n_response(query="网球王子")))
