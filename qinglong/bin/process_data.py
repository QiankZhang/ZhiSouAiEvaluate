#! -*- encoding: utf-8 -*-

import os
import math
import json
import asyncio
import hashlib
import pandas as pd
from pathlib import Path
from typing import Any, Callable
from src.redis_helper.user_behaviour import get_user_behaviour
from src.custom_data_api import get_hbase, get_pid_analysis_summary

    
async def process_jsonl(input_path: str, output_path: str) -> None:
    """
    Args:
        input_path:  输入文件路径
        output_path: 输出文件路径
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(input_path, "r", encoding="utf-8") as fin, open(output_path, "w", encoding="utf-8") as fout:

        for line_num, line in enumerate(fin, 1):
            line = line.strip()
            if not line:
                continue

            record = json.loads(line)
            pid_list = record.get("pid_order", [])
            record["pid_desc_analysis_order"] = []
            try:
                if len(pid_list) > 0:
                    # 图片分析结果;get_pid_analysis_summary
                    pid_tasks = [get_pid_analysis_summary(pid=item.get("pid", ""), desc=item.get("desc", "")) for item in pid_list]
                    pid_res = await asyncio.gather(*pid_tasks, return_exceptions=True)

                    for item in pid_res:
                        p_id = item.get("data", {}).get("pid", "")
                        res = item.get("data", {}).get("content", "").replace("</think>","")
                        desc = item.get("desc", "")
                        record['pid_desc_analysis_order'].append({"pid": p_id, "desc": desc ,"analysis": res})
                else:
                    print(pid_list)
            except Exception as e:
                pass
                
            record.pop("pid_order", None)
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            fout.flush()


async def main():
    """
    路径可由环境变量注入（评估平台子进程调用）：
      QINGLONG_INPUT   make_data 产出的 jsonl
      QINGLONG_OUTPUT  补齐图片分析后的 jsonl（逐行追加，供外部读取进度）
    """
    # 先把pid推送到队列,然后获取结果
    input_path = (os.environ.get("QINGLONG_INPUT", "") or "").strip() or "./results/data_0902_zy.jsonl"
    output_path = (os.environ.get("QINGLONG_OUTPUT", "") or "").strip() or "./results/data_0902_zy_v2.jsonl"
    await process_jsonl(input_path=input_path, output_path=output_path)

if __name__=="__main__":
    """
    """
    asyncio.run(main())
    
