#! -*- encoding: utf-8 -*-

"""
    定义mid的sence_tag,类别可以动态更新
"""
import os
import sys
import asyncio

from src.utils import sort_by_score_desc
from src.custom_data_api import fetch_zhisou_ret
from src.redis_helper.mid_hot_query import get_mid_hot_query


async def mid_map_hot_search(mid:str= "", log=None) -> dict:
    """
        判断mid映射到的query是否为热搜,如果是热搜,需要计算query对应的智搜结果、query、热搜标签
    """
    result = {}
    hot_search_zhisou_res = await get_mid_hot_query(mid=mid, log=log)

    if len(hot_search_zhisou_res) > 0:
        result["sence_tag"] = "热搜"
        hot_query = hot_search_zhisou_res.get("queries",[])
        result["hot_mid_query"] = hot_query[0]

        zhisou_res = await fetch_zhisou_ret(query=hot_query[0], log=log)
        result["hot_mid_search_zhisou"] = zhisou_res
    else:
        result["sence_tag"] = "其他"
        result["hot_mid_query"] = ""
        result["hot_mid_search_zhisou"] = ""

    return result


async def mid_map_domain(domain_path:str="", m3_metadata:str="", log=None) -> dict:
    """
        判断是否属于config/domain.txt中的某一个领域
    """ 
    sence_tag_str = ""   
    try:
        m3_metadata_dict = eval(m3_metadata)
        r1_str_info = m3_metadata_dict.get("r1", "")
        m1_str_info = m3_metadata_dict.get("m1", "")
        sence_tag_str_info = r1_str_info or m1_str_info

        sence_tag_score = sort_by_score_desc(text=sence_tag_str_info)
        sence_tag_str = sence_tag_score[0][0]
    except Exception as e:
        if log:
            log.error(f"mid map domain failed, m3_metadata: {m3_metadata}")
        return {}

    with open(domain_path, "r") as reader:
        for line in reader:
            line = line.strip()
            if line in sence_tag_str:
                return {"sence_tag": line}
    
    return {}

