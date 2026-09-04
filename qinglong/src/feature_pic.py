#! -*- encoding: utf-8 -*-

"""
    获取mid中图片对应的信息, 例如pid、description、analysis、ocr
"""
import os
import sys
import json
import asyncio
import requests

from src.custom_data_api import build_pid_analysis_task


async def fetch_feature_for_pic(mid:str="", hbase_res=None,log=None) -> dict:
    """
        1. 从Hbase的PIC字段中获取pid,不同pid用tab分割;
        2. 从Hbase的PIC_DESCRIPTION字段获取pid、desc, 这里pid的顺序与博文中图片的展示顺序不一致;
        3. pid推送到图片分析计算队列,这里不获取计算结果,因为图片分析计算耗时平均3秒;
        4. 按照PIC字段中的顺序,重新排列
    """
    result = {}
    result['pid_order'] = []

    try:
        pids_desc = hbase_res.get("PIC_DESCRIPTION", "[]")
        pids_desc_list = eval(pids_desc)
    except Exception as e:
        pids_desc_list = []

    try:
        pids_str = hbase_res.get("PIC","")
        if pids_str:
            pids_list = pids_str.strip().split("\t")

            for item in pids_list:
                temp = {}
                temp["pid"] = item
                temp["desc"] = ""

                # 图片分析结果;首先，把pid推送到计算队列，后面在取‘pid_analysis’的值
                await build_pid_analysis_task(pid=str(item), log=log)

                for desc_dict in pids_desc_list:
                    if item in desc_dict['pid']:
                        temp["desc"] = desc_dict.get("desc", "")
                
                result['pid_order'].append(temp)
    except Exception as e:
        if log:
            log.error(f"fetch PIC from hbase failed, mid:{mid}", exc_info=True)

    return result