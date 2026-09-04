#! -*- encoding: utf-8 -*-

"""
    获取mid对应的功能入口:功能说明,具体内容由产品定义
"""
import os
import sys
import json
import asyncio
import requests


def mid_function_guide_hongzhong(mid:str="", log=None):
    """
    """

    for i in range(3):
        try:
            url = "http://getdata.search.weibo.com/getdata/querydata2.php?condition=%s&mode=weibo&format=json&hbase=1" % (mid)
            req = requests.get(url)
            res = req.text
            res = json.loads(res)

            show_video_summary = False
            article_summary_eligible = False
            comment_summary_eligible = False
            image_analysis_eligible = False
            fact_checking_eligible = True
            video_recognition_eligible= False
            plot_interpretation_eligible = False
            related_video_eligible = False
            person_recognition_eligible = False

            if isinstance(res, dict):
                filter_str =int(res.get("FILTER","0"))
                video_flag = True if filter_str & 16 else False
                pic_flag = True if filter_str & 1 else False
                if  pic_flag:
                    image_analysis_eligible = True
                video_voice = res.get("VIDEO_VOICE","")
                content = res.get("LONGTEXT","") if res.get("ISLONG","") == "1" else res.get("CONTENT","")
                video_voice = res.get("VIDEO_VOICE","")
                pic_feature = json.loads(res.get("PICS_FEATURE", "{}"))
                ocr_text = ""
                if pic_feature:
                    txt = "".join([item['ocr'] for item in pic_feature['res'] if 'ocr' in item])
                    is_ocr = True
                    if is_ocr:
                        ocr_text = txt
                if len(video_voice) >= 250:
                    show_video_summary = True
                if video_flag:
                    related_video_eligible = True
                
                if len(content) + len(ocr_text)  >= 350:
                    article_summary_eligible = True
                cmt_num = int(res.get("CMTNUM","0"))
                valid_cmt_num = int(res.get("VALIDCMTNM","0"))
                if (cmt_num * valid_cmt_num)/1000 >= 30:
                    comment_summary_eligible = True

                VERIFIED_TYPE_EXT = res.get("VERIFIED_TYPE_EXT")
                if VERIFIED_TYPE_EXT:
                    VERIFIED_TYPE_EXT = int(VERIFIED_TYPE_EXT)
                else:
                    VERIFIED_TYPE_EXT = 0
                
                try:
                    VERIFIEDTYPE = int(res.get("VERIFIEDTYPE",0))
                except Exception as e:
                    VERIFIEDTYPE = 0

                all_tag_new = res.get("ALL_TAG_NEW","")
                if (VERIFIED_TYPE_EXT ==53 and VERIFIEDTYPE== 3) or  VERIFIEDTYPE in [1,2,3,4,5,6,7] :
                    fact_checking_eligible = False
                for cate1 in ["美女","帅哥","搞笑","舞蹈","美食"]:
                    if cate1 in all_tag_new:
                        fact_checking_eligible = False
                        break
                for cate1 in ["电影","电视剧","综艺"]:
                    if cate1 in all_tag_new and video_flag:
                        video_recognition_eligible = True
                        plot_interpretation_eligible = True
                        break
                for cate1 in ["美女","帅哥"]:
                    if cate1 in all_tag_new and video_flag:
                        person_recognition_eligible = True
                        break
                
                return show_video_summary, article_summary_eligible, comment_summary_eligible , fact_checking_eligible, video_recognition_eligible, related_video_eligible

        except Exception as e:
            if log:
                log.error(f"Error in feature entry\tmid: {mid}", exc_info=True)
    
    return False, False, False, False, False, False


def mid_function_guide(mid:str="", hbase_res=None, log=None):
    """
    """
    show_video_summary = False
    article_summary_eligible = False
    comment_summary_eligible = False
    fact_checking_eligible = True
    video_recognition_eligible= False
    related_video_eligible = False

    if isinstance(hbase_res, dict):

        filter_str =int(hbase_res.get("FILTER","0"))
        video_flag = True if filter_str & 16 else False
        pic_flag = True if filter_str & 1 else False

        video_voice = hbase_res.get("VIDEO_VOICE","")
        content = hbase_res.get("LONGTEXT","") if hbase_res.get("ISLONG","") == "1" else hbase_res.get("CONTENT","")
        video_voice = hbase_res.get("VIDEO_VOICE","")
        pic_feature = json.loads(hbase_res.get("PICS_FEATURE", "{}"))
        ocr_text = ""
        if pic_feature:
            txt = "".join([item['ocr'] for item in pic_feature['res'] if 'ocr' in item])
            is_ocr = True
            if is_ocr:
                ocr_text = txt
        if len(video_voice) >= 250:
            show_video_summary = True
        if video_flag:
            related_video_eligible = True
        
        if len(content) + len(ocr_text)  >= 350:
            article_summary_eligible = True

        cmt_num = int(hbase_res.get("CMTNUM","0"))
        valid_cmt_num = int(hbase_res.get("VALIDCMTNM", 0))
        if (cmt_num * valid_cmt_num)/1000 >= 30:
            comment_summary_eligible = True

        VERIFIED_TYPE_EXT = hbase_res.get("VERIFIED_TYPE_EXT")
        if VERIFIED_TYPE_EXT:
            VERIFIED_TYPE_EXT = int(VERIFIED_TYPE_EXT)
        else:
            VERIFIED_TYPE_EXT = 0
        try:
            VERIFIEDTYPE = int(hbase_res.get("VERIFIEDTYPE",0))
        except Exception as e:
            VERIFIEDTYPE = 0

        all_tag_new = hbase_res.get("ALL_TAG_NEW","")

        if (VERIFIED_TYPE_EXT ==53 and VERIFIEDTYPE== 3) or  VERIFIEDTYPE in [1,2,3,4,5,6,7] :
            fact_checking_eligible = False

        for cate1 in ["美女","帅哥","搞笑","舞蹈","美食"]:
            if cate1 in all_tag_new:
                fact_checking_eligible = False
                break
        for cate1 in ["电影","电视剧","综艺"]:
            if cate1 in all_tag_new and video_flag:
                video_recognition_eligible = True
                plot_interpretation_eligible = True
                break

        for cate1 in ["美女","帅哥"]:
            if cate1 in all_tag_new and video_flag:
                person_recognition_eligible = True
                break
        
        return show_video_summary, article_summary_eligible, comment_summary_eligible , fact_checking_eligible, video_recognition_eligible, related_video_eligible


ABILITY_NAME_MAP = {
    "show_video_summary": "视频总结", 
    "article_summary_eligible": "博文总结", 
    "comment_summary_eligible": "评论总结",
    "fact_checking_eligible": "信息求证",
    "video_recognition_eligible": "影视识别",
    "plot_interpretation_eligible": "剧情解读",
    "related_video_eligible": "相关视频",
    "person_recognition_eligible": "人物识别", #
}

FEATURE_ENTRY_MAP = {
    "视频总结": "帮我总结一下视频内容", 
    "博文总结": "帮我总结一下这篇博文说了什么", 
    "评论总结": "帮我总结一下评论中的观点",
    "信息求证": "帮我核实一下真假",
    "影视识别": "帮我识别一下这部影视作品",
    "相关视频": "帮我找找类似的视频",
}


def fetch_feature_entry_mid(mid:str="", hbase_res=None,log=None) -> dict:
    """

    """
    result = {}
    result["feature_entry"] = []
    show_video_summary, article_summary_eligible, comment_summary_eligible , fact_checking_eligible, video_recognition_eligible, related_video_eligible = mid_function_guide(mid=mid, hbase_res=hbase_res, log=log)
    
    eligible_map = {
        "show_video_summary": show_video_summary,
        "article_summary_eligible": article_summary_eligible,
        "comment_summary_eligible": comment_summary_eligible,
        "fact_checking_eligible": fact_checking_eligible,
        "video_recognition_eligible": video_recognition_eligible,
        "related_video_eligible": related_video_eligible,
    }

    for ability_key, eligible in eligible_map.items():
        if eligible:
            name = ABILITY_NAME_MAP.get(ability_key, "")
            entry = FEATURE_ENTRY_MAP.get(name, "")
            if name and entry:
                result["feature_entry"].append(f"{name}:{entry}")
    

    return result


if __name__ == "__main__":
    """
    """
    result = mid_function_guide(mid="5328133311169780")
    print(result)
    print(fetch_feature_entry_mid(mid="5328133311169780"))