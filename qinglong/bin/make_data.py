#! -*- encoding:utf-8 -*-
"""
通过mid获取各种物料,用于生成追问
    - mid: mid
    - mid_cotent: 博文内容
    - source: 来源
    - hot_mid_query: mid对应的热搜query
    - hot_mid_search_zhisou: 热搜query对应的智搜结果
    - sence_tag: 类别标签
    - feature_entry: 功能入口:功能说明
    - pid_order: 图片pid,按照博文中的顺序排列, 会出现缺失图片的情况
    - pid_analysis_order: 图片pid、图片分析结果, 按照博文中的顺序排列
    - pid_url_description: 图片pid以及图片描述
    - blog_summary: 博文总结
    - video_summary: 视频总结
    - comment_summary: 评论总结
    - aigc_abstract: 智汇总结
    - valid_cmt_num: 有效评论数
    - p_time: 发博时间
    - nick: 发博者昵称
    - user_zhisou: 人物智搜结果,针对于明星
    - blog_video_pic_comment: 博文视频或图片及评论概要
    - user_behaviour: 用户行为
    - voice2text: 音转文内容
    - pic_ocr_info: 图像OCR、后面也会增加pic_description
    - tag_blog: tag标签,分数值最大的query,返回对应的mid、博文内容、音转文、图像OCR、视频信息、发博者类型、质量分、相关性分
    - m3_blog: 3级标签,分数值最大的query,返回对应的mid、博文内容、音转文、图像OCR、视频信息、发博者类型、质量分、相关性分
    - reposted_blog: 博文为转发博文,获取原始博文的博文内容、音转文、图像OCR、视频信息
"""


import re
import os
import ast
import sys
import math
import time
import json
import asyncio
import aiohttp
import requests
import pandas as pd

import hmac
import base64
import hashlib
import random
import urllib.parse

from hashlib import sha1
from datetime import datetime
from urllib import request, parse
from typing import Optional, Dict, Optional


from src.llm import LLMWeibo
from src.base import BaseTask
from src.logger import get_logger
from src.user_behaviour import get_statis_data
from src.hot_comment import get_all_comment_by_page
from src.redis_helper.comment_summary import get_comment_summary
from src.redis_helper.blog_video_summary import get_blog_video_summary
from src.redis_helper.user_behaviour import get_user_behaviour

from src.custom_data_api import (
    build_pid_analysis_task,
    get_tag_m3_blog,
    get_ocr_voice_info,
    get_hbase,
    search_people_zhisou,
    search_people,
)

from src.utils import delete_wbcustomblock
from src.feature_pic import fetch_feature_for_pic
from src.feature_entry_mid import fetch_feature_entry_mid
from src.define_mid_sence import mid_map_hot_search, mid_map_domain


class SubTask(BaseTask):
    """
    """
    def __init__(self, logger, session, llm_func, post_func, domain_path):
        """
        """
        super().__init__(logger=logger)
        self.session = session
        self.llm_func = llm_func
        self.post_func = post_func
        self.domain_path = domain_path

    def read_metadata_txt(self, source_file: str = "") -> list:
        """
            读取txt文件
        """
        result = []
        seen = set()
        try:
            with open(source_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    mid = line.strip()
                    if mid and mid not in seen:
                        seen.add(mid)
                        result.append([{'mid': mid}])
        except Exception as e:
            self.log.error(f"Error reading {source_file}: {e}")
            return []

        return result

    async def tag_m3_material_process(self, query:str="") -> list:
            """
                通过query, 搜索相关内容; 输入query,返回top10相关博文的mid和相关分数
            """
            if not query:
                return []

            result = []
            related_mids_info = await get_tag_m3_blog(query=query, log=self.log)
            
            user_category_list = related_mids_info.get('struct_content_list',[])
            related_scores = related_mids_info.get('raw_material_list',[])

            # 1. 构建map映射，key为mid，value为[质量分,相关性分]
            score_map = {}
            for r_score in related_scores:
                authoritative_features = r_score.get("authoritative_features", {})
                try:
                    authoritative_features_dict = eval(authoritative_features)
                except Exception as e:
                    authoritative_features_dict = {}

                related_mid = r_score.get("mid", "")
                hit_score_final = authoritative_features_dict.get("hit_score_final", 0)
                final_qi_score = authoritative_features_dict.get("final_qi_score", 0)

                score_map[related_mid] = [hit_score_final, final_qi_score]

            # 2. 遍历user_category_list，根据score_map，拿到对应的发布账号类型
            for item in user_category_list:
                account_type = item.get("发布账号类型", "")
                mid = item.get("mid", "")
                if mid in score_map:
                    temp_hit, temp_qi = score_map[mid][0], score_map[mid][1]
                    if float(temp_hit) >= 70 and float(temp_qi) >=38:
                        sub_task_res = await self.build_metadata(str(mid), need_comment=False)
                        tag_m3_hbase_res = await get_hbase(str(mid), log=self.log)
                        result.append({
                            "mid": mid,
                            "content": item.get("内容", ""),
                            "voice2text": tag_m3_hbase_res.get("VIDEO_VOICE",""),
                            "pic_ocr_info": tag_m3_hbase_res.get("IDX_OCR_TEXT",""),
                            "video_info": sub_task_res.get("video_info",""),
                            "account_type": account_type,
                            "hit_score_final": temp_hit,
                            "final_qi_score": temp_qi
                            }
                        )
                        if len(result) >= 10:
                            return result

            return result

    async def build_metadata(self, mid:str = "", need_comment:bool=True) -> dict:
        """
        """
        if need_comment:
            comment_res = await get_all_comment_by_page(mid=mid, count=200, c2_size=10, sort="hot", retry=3, log=self.log)
            # 根据热度博文评论区数据, 只保留一级评论
            sorted_total_comment_list = sorted(comment_res, key=lambda x: x["likes_and_replies"], reverse=True)

        # 获取视频总结
        video_res = await get_blog_video_summary(mid=mid, postfix="video_summary", log=self.log)
        video_info = video_res.get("summary", {}).get("content", "")

        return {
            "mid": mid,
            "video_info": video_info,
            "hot_comment": sorted_total_comment_list[:10] if need_comment else []
        }

    async def process(self, meta_info:dict={}, session:aiohttp.ClientSession=None, semaphore:asyncio.Semaphore=None):
        """
        """
        mid = meta_info['mid']
        structed_info = {}
        hbase_res = await get_hbase(str(mid), log=self.log)

        structed_info["mid"] = mid
        structed_info["hot_mid_search_zhisou"] = ""
        structed_info["hot_mid_query"] = ""
        structed_info["sence_tag"] = "其他"
        structed_info["feature_entry"] = []

        # 获取对应的功能入口:功能说明
        feature_entry_res = fetch_feature_entry_mid(mid=str(mid), hbase_res=hbase_res, log=self.log)
        structed_info.update(feature_entry_res)

        # 判断是否为热搜
        mid_map_hot_search_res = await mid_map_hot_search(mid=str(mid), log=self.log)
        structed_info.update(mid_map_hot_search_res)
        
        # 判断类别
        m3_metadata = hbase_res.get("ALL_TAG_NEW", "{}")
        mid_map_domain_res = await mid_map_domain(domain_path=self.domain_path, m3_metadata=m3_metadata, log=self.log)
        structed_info.update(mid_map_domain_res)

        # 获取图片特征: pid、desc、analysis
        pic_feature_res = await fetch_feature_for_pic(mid=str(mid), hbase_res=hbase_res,log=self.log)
        structed_info.update(pic_feature_res)

        # 博文总结、视频总结、评论总结
        blog_summary, comment_summary = await asyncio.gather(
            get_blog_video_summary(mid=mid, postfix="blog_summary", log=self.log),
            get_comment_summary(mid=mid, log=self.log)
        )

        structed_info["blog_summary"] = blog_summary.get("summary", {}).get("content", "")
        structed_info["comment_summary"] = comment_summary.get("summary", {}).get("content", "")

        # 智汇总结
        structed_info["aigc_abstract"] = ""
        try:
            structed_info["aigc_abstract"] = eval(hbase_res.get("AIGC_ABSTRACT", "{}")).get("total_abstract","")
        except Exception as e:
            self.log.error(f"fetch aigc abstract failed\tmid: {mid}")
        
        # 有效评论数
        cmt_num = int(hbase_res.get("CMTNUM", 0))
        valid_cmt_num = int(hbase_res.get("VALIDCMTNM", 0))
        cmt_num = math.ceil(cmt_num * valid_cmt_num / 1000)
        structed_info["valid_cmt_num"] = cmt_num

        # p_time and nick
        structed_info["p_time"] = hbase_res.get("TIME", "")
        nick = hbase_res.get("NICK", "")
        structed_info["nick"] = nick
        # 
        structed_info["user_page"] = []
        structed_info["user_zhisou"] = ""

        if "明星" in structed_info['sence_tag']:
            # 明星：智搜关于博主的结果(人物版) ;
            res_user_zhisou = await search_people_zhisou(query=nick, log=self.log)
            # result['analysis_result_data']['msg']
            user_zhishou = res_user_zhisou.get("analysis_result_data", {}).get("msg", "")
            user_zhishou = user_zhishou.strip().split('</think>')
            structed_info["user_zhisou"] = delete_wbcustomblock(user_zhishou[-1])

        # 博文数据
        mid_content = hbase_res.get("LONGTEXT", "") if hbase_res.get("ISLONG", "") == "1" else hbase_res.get("CONTENT", "")
        structed_info["mid_content"] =mid_content

        # 博文视频或图片及评论概要
        structed_info["blog_video_pic_comment"] = hbase_res.get("IDX_COMPREHEND_ABSTRACT", "").strip()
        
        # 评论、视频帧、音转文、图片ocr
        comment_video_info = await self.build_metadata(str(mid))
        structed_info.update(comment_video_info)
        structed_info["voice2text"] = hbase_res.get("VIDEO_VOICE", "")
        structed_info["pic_info"] = hbase_res.get("IDX_OCR_TEXT", "")

        # 用户行为数据
        try:
            user_behaviour = await get_user_behaviour(str(mid))
            structed_info['user_behaviour'] = user_behaviour.get('follow_queries', [])
        except Exception as e:
            structed_info['user_behaviour'] = []
            
        # 
        a = structed_info["voice2text"]
        b = structed_info["pic_info"]

        if len(a + b + mid_content) < 50 and cmt_num <= 20:
            # tag和三级标签(m3)
            tag_str = hbase_res.get("TAG", "")
            # m3_metadata = hbase_res.get("ALL_TAG_NEW", {})
            try:
                m3_metadata_dict = eval(m3_metadata)
                m3_str_info = m3_metadata_dict.get("m3", "")

                if m3_str_info:
                    m3_q_score = sort_by_score_desc(text=m3_str_info)
                    m3_str = m3_q_score[0][0]
                else:
                    m3_str = ""
            except Exception as e:
                m3_str = ""

            tag_info, m3_info = await asyncio.gather(
                self.tag_m3_material_process(query=tag_str),
                self.tag_m3_material_process(query=m3_str)
            )
            structed_info['tag_blog'] = tag_info
            structed_info['m3_blog'] = m3_info
            structed_info['is_poor'] = True
        else:
            structed_info['tag_blog'] = []
            structed_info['m3_blog'] = []
            structed_info['is_poor'] = False

        # 先取FILTER , 然后转成二进制 , 如果第三位是1才是转发博文；然后拿到'ROOTMID'是原博文的mid
        reposted_blog_mid = hbase_res.get("ROOTMID", "").strip()
        structed_info['reposted_blog'] = []
        filter_flag = int(hbase_res.get("FILTER", 0) or 0) & 4

        if filter_flag and reposted_blog_mid:
            self.log.info(f'reposted_blog_mid:{reposted_blog_mid}')
            reposted_res, reposted_hbase_res = await asyncio.gather(
                self.build_metadata(str(reposted_blog_mid),need_comment=False),
                get_hbase(str(reposted_blog_mid), log=self.log)
            )
            structed_info['reposted_blog'].append({
                "reposted_blog_mid": reposted_blog_mid,
                "content": reposted_hbase_res.get("LONGTEXT", "") if reposted_hbase_res.get("ISLONG", "") == "1" else reposted_hbase_res.get("CONTENT", ""),
                "voice2text": reposted_hbase_res.get("VIDEO_VOICE",""),
                "pic_ocr_info": reposted_hbase_res.get("IDX_OCR_TEXT",""),
                "video_info": reposted_res.get("video_info","")
                }
            )

        return structed_info

    def save_jsonl(self, results, target_file):
        """
        """
        with open(target_file, "w", encoding="utf-8") as f:
            for record in results:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _env(name: str, default: str) -> str:
    """读环境变量，空值回退到默认（保持脚本单独运行时的原有硬编码行为）。"""
    return (os.environ.get(name, "") or "").strip() or default


async def main(debug:bool=True):
    """
    路径与并发可由环境变量注入，供外部编排（评估平台子进程调用）按行数读取进度：
      QINGLONG_SOURCE  待解析 mid 列表 txt
      QINGLONG_TARGET  输出 jsonl（每解析完一条立即追加一行）
      QINGLONG_CONCURRENCY / QINGLONG_BASE_PATH / QINGLONG_DOMAIN_PATH
    """
    # 全局日志对象
    date_info = datetime.now().strftime("%Y-%m-%d")
    log = get_logger("./logs",date_info=date_info)
    #log = None
    # 限制并发数，防止被风控
    max_concurrent = int(_env("QINGLONG_CONCURRENCY", "10"))
    semaphore = asyncio.Semaphore(max_concurrent)
    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=200))

    base_path = _env("QINGLONG_BASE_PATH", "/data1/minisearch/upload/qinglong")
    domain_path = _env("QINGLONG_DOMAIN_PATH", f"{base_path}/config/domain.txt")
    source_file = _env("QINGLONG_SOURCE", f"{base_path}/data/mid_zy.txt")
    target_file = _env("QINGLONG_TARGET", f"{base_path}/results/data_0902_zy.jsonl")

    llm_obj = LLMWeibo(logger=log, sub_source="qinglong")
    task_obj = SubTask(logger=log, session=session, llm_func=llm_obj.call_llm_base_async, post_func=llm_obj.postprocess_qwen, domain_path=domain_path)

    mid_candidate = task_obj.read_metadata_txt(source_file = source_file)
    log.info(len(mid_candidate))

    # 增量落盘：单条解析失败不阻塞整体，落一行 {"mid":..., "_error":...}，
    # 外部靠输出文件行数感知进度。
    os.makedirs(os.path.dirname(target_file) or ".", exist_ok=True)

    async def _run_one(meta_info: dict) -> dict:
        async with semaphore:
            try:
                return await task_obj.process(meta_info)
            except Exception as e:  # noqa: BLE001 - 单条失败落错误行，不中断批处理
                log.error(f"process mid failed\tmid:{meta_info.get('mid', '')}\t{e}", exc_info=True)
                return {"mid": meta_info.get("mid", ""), "_error": str(e)}

    pending = [asyncio.create_task(_run_one(args[0])) for args in mid_candidate]
    with open(target_file, "w", encoding="utf-8") as f:
        for fut in asyncio.as_completed(pending):
            record = await fut
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
    await task_obj.session.close()


if __name__ == "__main__":
    """
    """
    asyncio.run(main(debug=True))
