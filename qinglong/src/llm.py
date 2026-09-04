#! -*- encoding: utf-8 -*-

import os
import time
import json
import asyncio
import aiohttp
import requests
from typing import List, Dict, Optional, Callable, Any


def token_loader(token_file):
    # 惰性读取：token 文件缺失时不在 import 期崩溃（评估平台 mid→物料 链路不调用 LLM，
    # 只是 import 了本模块）。文件存在时行为与原来一致。
    token = None
    token_update_time_sec = 0
    try:
        token_update_time_sec = int(os.path.getmtime(token_file))
        token = open(token_file).readline().strip()
    except OSError:
        pass

    def wrapper():
        nonlocal token
        nonlocal token_update_time_sec
        now_sec = int(time.time())
        if token is None or now_sec - token_update_time_sec > 3600:
            try:
                token = open(token_file).readline().strip()
                token_update_time_sec = now_sec
            except OSError:
                return ""
        return token
    return wrapper


load_c_token = token_loader(r'/data1/minisearch/upload/token/c_token_file')


def get_c_token():
    token_str = load_c_token()
    piece = token_str.split(':')
    if len(piece) < 2:
        return {}
    return {piece[0].strip(): piece[1].strip()}


class LLMWeibo():

    def __init__(self, logger=None,sub_source=""):
        """
        """
        self.log = logger
        self.sub_source = sub_source

    async def call_llm_base_async(self,
            meta_info:list=[],
            messages:list=[], 
            tools_avaiable:list=[], 
            model_id:str="", 
            request_type:str="", 
            enable_thinking:bool=False, 
            repeat_penalty:int=1.0,
            temperature:float=0.1, 
            max_tokens:int=10240,
            enable_tools:bool=False,
            disable_tools_force:bool=False,
            session=None
        ):
        """
            claude 不支持enable_thinking和repeat_penalty, 后面AIGC也许会修改
            请求和后处理分开,方便对不同的模型进行处理
        """
        headers = get_c_token()

        url = 'http://i.aigc.weibo.com/completion'
        
        params = {
            'message': '你好',
            'appkey': '2165752702',
            'type': request_type,
            "smart_schedule": 1,
            'use_ext_first': 1,
            'sub_source': self.sub_source,
            'model_id': model_id
        }

        model_ext = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # 思考模式
        if enable_thinking:
            model_ext['enable_thinking'] = enable_thinking
            model_ext['repeat_penalty'] = repeat_penalty
        else:
            model_ext['enable_thinking'] = False

        # 使用工具
        if enable_tools:
            model_ext['tools'] = tools_avaiable

        # 强制不使用工具
        if disable_tools_force:
            model_ext['tool_choice'] = 'none'

        
        payload = json.dumps({
            "api_ext": {
                "request_compatible_mode": "openai",
                "X-DashScope-DataInspection": {
                    "input": "disable",
                    "output": "disable"
                }
            },
            "model_ext": model_ext
        }, ensure_ascii=False)

        try:
            async with session.post(url=url, headers=headers, params=params, data=payload.encode('utf-8')) as response:
                text = await response.text()
                try:
                    res = json.loads(text)
                except:
                    self.log.error("JSON格式解析失败" , exc_info=True)
                    return [], {}

            return meta_info, res
        except Exception as e:
            if self.log:
                self.log.error(f"调用LLM模型失败, {meta_info[0]}", exc_info=True)  
            else:
                print(f"调用LLM模型失败, {meta_info[0]}")

        return meta_info, {}

    def postprocess_claude(self, res:dict={}):
        """
        """
        try:
            content = res["response_data"]['content'][0]['text']
            return [content]
        except Exception as e:
            if self.log:
                self.log.error(f"后处理解析结果失败,", exc_info=True)  
            else:
                print(f"后处理解析结果失败, {meta_info[0]}")
        return []

    def postprocess_qwen(self, res:dict={}):
        """
        """
        try:
            message = res["response_data"]["choices"][0]["message"]
            tool_calls = message.get("tool_calls", [])
            reasoning_content = message.get("reasoning_content", "")
            content = message["content"]
            return [reasoning_content, content, tool_calls]
        except Exception as e:
            if self.log:
                self.log.error(f"后处理解析结果失败,", exc_info=True)  
            else:
                print(f"后处理解析结果失败, {meta_info[0]}")
        return []
