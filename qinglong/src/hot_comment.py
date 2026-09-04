#！ -*- encoding:utf-8 -*-

import time
import json
import asyncio
import aiohttp
import requests
import datetime
from typing import Any, Dict, List, Optional

"""
林虎提供，用户获取评论区数据
"""

async def fetch_comment_by_mid_hot(mid, page=1, c1_size=200, c2_size=10, retry=3, log=None):
    """
    """
    if c1_size > 200:
        c1_size = 200
    if c2_size > 10:
        c2_size = 10

    url = f"http://i.search.weibo.com/search/wis/comment.json?mid={mid}&page={page}&pagesize={c1_size}&child_comment_count={c2_size}&sid=i_ai_model&sort=hot"

    comment_list, max_id_type = [], 0

    for attempt in range(retry):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2000)) as session:
                async with session.get(url) as resp:
                    text = await resp.text()
                    res = json.loads(text)
                    if isinstance(res, dict) and res:

                        c1_key = "root_comments"
                        c1_comment_list = res.get("data", {}).get(c1_key, [])
                        max_id_type = res.get("data", {}).get("max_id_type", 0)

                        for _, c1_dict in enumerate(c1_comment_list, 1):

                            like_count = c1_dict.get("like_count", 0)
                            reply_count = c1_dict.get("reply_count", 0)
                            like_reply = int(like_count) + int(reply_count)

                            c_info = {
                                "content": c1_dict.get("text", ""), 
                                "id": c1_dict.get("idstr", ""), 
                                "likes": like_count,
                                "replies": reply_count,
                                "likes_and_replies": like_reply
                                }
                            if c1_dict.get("cmt_ext", "") == "level_type:1":
                                comment_list.append(c_info)

                        return {"page": page, "comment_list": comment_list, "max_id_type": max_id_type, "sort": "hot"}
        except asyncio.TimeoutError:
            if log:
                log.error(f"fetch_comment_ask_timeout", exc_info=True)
        except Exception as e:
            if log:
                log.error(f"fetch_comment_error", exc_info=True)

    return {}


async def get_all_comment_by_page(mid, count=500, c2_size=10, sort="hot", retry=1, log=None):
    """
    """
    try:
        # 并发获取所有页的评论
        max_comment_byte_size, tasks = 50000, []

        task = fetch_comment_by_mid_hot(mid, page=1, c1_size=200, c2_size=c2_size, retry=retry, log=log)
        tasks.append(task)

        results = await asyncio.gather(*tasks)
        
        flag_stop_flag = False
        total_comment_list = []
        total_id_set = set()
        total_byte_count = 0
        full_flag = False
        comment_count_flag = False

        for _, result in enumerate(results, 1):
            try:
                if len(total_comment_list) >= count:
                    comment_count_flag = True
                    break
                page = result.get("page", 0)
                _result = result.get("comment_list", [])
                max_id_type = result.get("max_id_type", 0)
                sort = result.get("sort")

                if sort == "hot":
                    if max_id_type == 1:
                        if not flag_stop_flag:
                            flag_stop_flag = True
                        else:
                            _result = []
                    else:
                        pass
                for comment_dict in _result:
                    if len(total_comment_list) >= count:
                        comment_count_flag = True
                        break
                    _id = comment_dict.pop("id", 0)
                    if _id not in total_id_set:
                        single_byte_count = len(str(comment_dict).encode("utf-8"))
                        if single_byte_count + total_byte_count > max_comment_byte_size:
                            full_flag = True
                            break
                        total_byte_count += single_byte_count
                        total_id_set.add(_id)
                        total_comment_list.append(comment_dict)
                    else:
                        pass
                if full_flag:
                    break
                if comment_count_flag:
                    break
            except Exception as e:
                if log:
                    log.error(f"error", exc_info=True)
        return total_comment_list
    except Exception as e:
        if log:
            log.error(f"mid: {mid}", exc_info=True)
    return []


if __name__ == "__main__":
    """
    """
    # mid = "5273154562036153"
    # mid = "5320626979740633"
    # mid = "5274885816323502"
    mid = "5274935846503067"
    # mid = "5275039559848433"
    # mid = "5271148936036882"

    total_comment_list = asyncio.run(get_all_comment_by_page(mid, 20000, 10))
    import pdb;pdb.set_trace()
    sorted_total_comment_list = sorted(total_comment_list, key=lambda x: x["likes_and_replies"], reverse=True)

    print(sorted_total_comment_list[:10])