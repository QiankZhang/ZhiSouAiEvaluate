#! -*- encoding: utf-8 -*-

"""

"""

import re


def delete_wbcustomblock(result: str) -> str:
    """
        ```wbCustomBlock``` 为自定义的块
    """
    re_quote = re.compile(r"<a>\[\d+\]</a>")
    result = re_quote.sub("", result)
    result = re.sub(r"```wbCustomBlock(.*?)```", "", result, flags=re.DOTALL)
    result = re.sub(r"<media-block>(.*?)</media-block>", "", result, flags=re.DOTALL)
    result = re.sub(r"<br>", "\n", result)
    return result


def remove_media_block(text):
    """
    """
    # 使用正则表达式匹配<media-block>标签及其内容（包括换行）
    pattern = r'<media-block>.*?</media-block>'
    # 使用re.DOTALL标志让.匹配换行符
    cleaned_text = re.sub(pattern, '', text, flags=re.DOTALL)
    # print(cleaned_text)
    pattern = r'```wbCustomBlock.*?```'
    cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.DOTALL)
    return cleaned_text.strip()  # 移除首尾空白


def sort_by_score_desc(text: str) -> list:
    """
        获取hbase中all_tag_new中的最高分query
    """
    items = [i.strip() for i in text.split("|") if i.strip()]
    data = []
    for item in items:
        parts = item.split("@")
        if len(parts) == 2:
            name, score_str = parts

            score = float(score_str)
            data.append((name, score))

    return sorted(data, key=lambda x: x[1], reverse=True)


if __name__=="__main__":
    """
    """
    content = ""
    print(sort_by_score_desc(text=content))