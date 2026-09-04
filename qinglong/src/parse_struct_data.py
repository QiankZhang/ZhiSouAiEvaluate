#! -*- encoding: utf-8 -*-

import re
from typing import Any


def parse_blocks(text: str) -> list[dict[str, Any]]:
    """
        解析现有格式的文本，返回结果列表
    """
    results = []
    
    # 按结果块拆分
    for m in re.finditer(r"\[结果 \d+ begin\](.*?)\[结果 \d+ end\]", text, re.DOTALL):
        block = m.group(1)
        result = {}
        
        # 提取所有字段
        for k, v in re.findall(r"\[([^]]+?) begin\](.*?)\[\1 end\]", block, re.DOTALL):
            result[k.strip()] = v.strip()
        
        results.append(result)
    
    return results


def add_comments_to_block(block_text: str, comments: list[dict]) -> str:
    """
        给一个结果块的文本末尾插入 comments 字段
    """
    try:
        block_text_new = re.sub(
            r"(\[结果 \d+ end\])",
            lambda m: f"    [comments begin]{comments}[comments end]\n{m.group(1)}",
            block_text,
            count=1
        )
        return block_text_new
    except Exception as e:
        import pdb;pdb.set_trace()
        print(block_text, e)
    
    return block_text


if __name__=="__main__":
    """
    """
    raw_text = """\n[结果 1 begin]\n    [type begin]微博[type end]\n    [username begin]我是林一同学[username end]\n    [content begin]（提醒账号：郭京飞） 钢蛋，我唱歌这么好笑吗，不看电视都没发现把你笑哭了 #地球超新鲜# http://t.cn/AXo6HrNc[content end]\n    [value tag begin]优质搜索结果[value tag end]\n    [date begin]2026年07月04日[date end]\n    [account type begin]大V账号[account type end]\n[结果 1 end]\n\n[结果 2 begin]\n    [type begin]微博[type end]\n    [username begin]地球超新鲜[username end]\n    [content begin]在#刘宇宁 干坏事的时候不嫌累#的主题下发布   #地球超新鲜# 地球团和新朋友一起在线陪你笑，高能名场面根本停不下来大家一起回看第一期“整蛊”（提醒账号：郭京飞） 和（提醒账号：我是林一同学） 的片段，当时地球团认真商量战术、互相加油打气，干劲满满到像在完成什么大任务（提醒账号：摩登兄弟刘宇宁） 看完直接锐评：人在“干坏事”的时候真的不嫌累，老有劲了咱就说搞事情地球团是认真的更多精彩reaction锁定（提醒账号：腾讯视频） #地球超新鲜2# 一起解锁更多快乐体验！ http://t.cn/AXo91Ev2[content end]\n    [value tag begin]优质搜索结果[value tag end]\n    [date begin]2026年07月05日[date end]\n    [account type begin]认证账号[account type end]\n[结果 2 end]\n"""

    matchs =  rebuild_data(data_str=raw_text)

    for match in matchs:
        import pdb;pdb.set_trace()
        if len(match)==7:
            print("结果序号:", match[0])
            print("类型:", match[1])
            print("用户名:", match[2])
            print("正文:", match[3])
            print("标签:", match[4])
            print("日期:", match[5])
            print("账号类型:", match[6])


    # parsed = parse_blocks(raw_text)
    # print("解析结果:", parsed)

    # 2. 添加评论
    # comments_data = [
    #     {"content": "哈哈哈哈", "likes": "1234", "replies": "567"},
    #     {"content": "郭京飞.....", "likes": "234", "replies": "89"},
    # ]

    # new_text = add_comments_to_block(raw_text, comments_data)
    # print("\n生成的目标格式:")
    # print(new_text)