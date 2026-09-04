"""
综搜底导问智搜功能引导 - 功能入口触发与排序模块 v5

规则：
  1. 意图输入：多个意图用 "|" 分隔，如 "Ip|ObjectiveFacts|UpdateCycle"
  2. 未匹配意图：自动忽略
  3. 排序优先级：信息求证 ＞ 近期动态 = 最新进展 ＞ 详细解读 ＞ 内容总结
  4. 互斥规则：同时命中「最新进展」和「近期动态」时，只保留「最新进展」
  5. 数量限制：最多展示 3 个功能入口
  6. 兜底策略：未命中任何功能 → 详细解读
  7. 每个功能始终附带文本标签
"""
import requests
from typing import List, Dict
import json
# ============================================================
# 1. 意图中英文映射
# ============================================================

INTENT_CN_MAP: Dict[str, str] = {
    "Star":                  "明星",
    "Couple":                "娱乐CP",
    "Person":                "人物",
    "Account":               "账号",
    "Ip":                    "IP词-作品",
    "LatestDevelopments":    "最新进展",
    "Event":                 "事件",
    "News":                  "资讯",
    "Gossip":                "吃瓜",
    "HotCircWord":           "热点流通词",
    "Interest":              "兴趣",
    "Verify":                "求证意图",
    "News_Strong":           "强资讯",
    "Question":              "问题型",
    "ContentIp":             "内容类IP",
    "Ip_Introduction":       "作品简介",
    "Ip_Encyclopedia":       "作品百科",
    "Ip_Evaluate":           "作品评价",
    "ShortTv":               "短剧",
    "Person_Introduction":   "人物简介",
    "Person_Encyclopedia":   "人物百科",
    "Star_Introduction":     "明星简介",
    "Leader_Introduction":   "领导人简介",
    "FamousPerson":          "名人意图",
    "ObjectiveFacts":        "客观事实",
    "News_Normal":           "中资讯",
    "News_Weak":             "弱资讯",
    "ExperienceGuide":       "经验攻略",
}


def intent_cn(tag: str) -> str:
    """将意图标签翻译为中文，未知标签返回原名"""
    return INTENT_CN_MAP.get(tag, tag)


def intents_cn(tags: list) -> str:
    """将意图标签列表翻译为中文逗号分隔字符串"""
    return ", ".join(f"{intent_cn(t)}({t})" for t in tags)


# ============================================================
# 2. 各功能入口的适配意图集合
# ============================================================

FEATURE_TRIGGER_INTENTS: Dict[str, set] = {
    "近期动态": {
        "Star", "Couple", "Person", "Account", "Ip",
    },
    "最新进展": {
        "LatestDevelopments", "Event", "News", "Gossip",
        "HotCircWord", "Interest", "Verify",
    },
    "详细解读": {
        "Event", "Gossip", "News_Strong", "HotCircWord",
        "Interest", "Verify", "Question",
    },
    "信息求证": {
        "Verify",
    },
    "内容总结": {
        "Ip",       # 作品简介        
        "ContentIp",             # 内容类IP
        "ShortTv",               # 短剧
        "Person",   # 人物百科
        "Star",     # 明星简介
        "Leader",   # 领导人简介
        "ObjectiveFacts",        # 客观事实
        "News",             # 弱资讯
        "Event",                 # 事件
        "Question",              # 问题型
        "ExperienceGuide",       # 经验攻略
        "Education",
        "Gossip"
    },
}

# ============================================================
# 3. 排序优先级（数值越小越高）
# ============================================================

FEATURE_PRIORITY: Dict[str, int] = {
    "信息求证": 1,
    "近期动态": 2,
    "最新进展": 2,
    "详细解读": 3,
    "内容总结": 4,
}

# ============================================================
# 4. 功能入口固定文本
# ============================================================

FEATURE_TEXT: Dict[str, str] = {
    "近期动态": "Ta最近有什么新动态",
    "最新进展": "帮我追踪一下最新进展",
    "详细解读": "帮我详细解读这个内容",
    "信息求证": "帮我核实一下真假",
    "内容总结": "帮我总结一下要点",
}

# ============================================================
# 5. 互斥规则
# ============================================================

MUTEX_RULES: List[Dict] = [
    {
        "features": {"最新进展", "近期动态"},
        "keep": "最新进展",
        "remove": "近期动态",
    },
]

# ============================================================
# 6. 最多展示数量
# ============================================================

MAX_FEATURES = 3

# ============================================================
# 7. 核心函数
# ============================================================

def get_triggered_features(query: str, intents_str: str) -> List[Dict]:
    """
    根据 query 和意图组合字符串，返回触发并排序后的功能入口列表。

    Args:
        query:       用户搜索词
        intents_str: 意图组合字符串，用 "|" 分隔

    Returns:
        排序后的功能入口列表（最多3个），每个元素为 dict：
        {
            "feature":            str,  # 功能名称
            "text":               str,  # 功能附带文本
            "priority":           int,  # 优先级
            "matched_intents":    list, # 命中意图（英文）
            "matched_intents_cn": str,  # 命中意图（中文）
        }
    """
    # ---- Step 1: 解析意图 ----
    intents = [i.strip() for i in intents_str.split("|") if i.strip()]

    # ---- Step 2: 遍历所有功能，检查触发 ----
    triggered: Dict[str, list] = {}
    for feature, intent_set in FEATURE_TRIGGER_INTENTS.items():
        for intent in intents:
            if intent in intent_set:
                triggered.setdefault(feature, []).append(intent)

    # ---- Step 3: 兜底策略 ----
    if not triggered:
        triggered["详细解读"] = []

    # ---- Step 4: 排序 ----
    results = []
    for feature, matched in triggered.items():
        results.append({
            "feature": feature,
            "text": FEATURE_TEXT[feature],
            "priority": FEATURE_PRIORITY.get(feature, 99),
            "matched_intents": matched,
            "matched_intents_cn": intents_cn(matched) if matched else "兜底",
        })
    results.sort(key=lambda x: x["priority"])

    # ---- Step 5: 互斥处理 ----
    for rule in MUTEX_RULES:
        present_features = {r["feature"] for r in results}
        if rule["features"].issubset(present_features):
            results = [r for r in results if r["feature"] != rule["remove"]]

    # # ---- Step 6: 截取前 MAX_FEATURES 个 ----
    # results = results[:MAX_FEATURES]

    return results


# ============================================================
# 8. 便捷封装
# ============================================================

def get_triggered_feature_names(query: str, intents_str: str) -> List[str]:
    """返回排序后的功能名称列表（简洁版）"""
    return [r["feature"] for r in get_triggered_features(query, intents_str)]


# ============================================================
# 9. 测试用例
# ============================================================
def get_query_intention(query):
    """
    """
    url = "http://huati.search.weibo.com/topic/intention.json?query={}".format(query)
    res = requests.get(url)
    res = json.loads(res.text)
    intention = res.get("res",{}).get("intention",{}).get("simple_level_1","")
    return intention


def query_function_guide(query):
    """
    """
    try:
        intents_str = get_query_intention(query)
        results = get_triggered_features(query, intents_str)
    except Exception as e:
        results = []

    return results


if __name__ == "__main__":
    query = "gmm涉事艺人中国粉丝站永久关站"
    results = query_function_guide(query)
    print(results)