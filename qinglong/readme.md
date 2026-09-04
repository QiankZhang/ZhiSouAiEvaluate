## 
```bash
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
```

1. 根据mid获取相关物料，执行脚本bin/make_data，这部分关于图片分析，是先把pid推动到队列
2. 获取图片分析结果，执行脚本bin/process_data

### 参数化（供外部编排调用，如评估平台子进程）

`bin/make_data` 与 `bin/process_data` 的输入 / 输出路径、并发可由环境变量注入，
不传时回退到脚本内原有硬编码默认值：

| 变量 | 作用 | 用于 |
|------|------|------|
| `QINGLONG_SOURCE` | 待解析 mid 列表 txt（每行一个 mid） | make_data |
| `QINGLONG_TARGET` | 物料 jsonl 输出（每解析完一条立即追加一行，含失败行 `{"mid":..,"_error":..}`） | make_data |
| `QINGLONG_CONCURRENCY` | 并发数（默认 10） | make_data |
| `QINGLONG_BASE_PATH` / `QINGLONG_DOMAIN_PATH` | 基础目录 / 分类词表路径 | make_data |
| `QINGLONG_INPUT` | make_data 产出的 jsonl | process_data |
| `QINGLONG_OUTPUT` | 补齐图片分析后的 jsonl（逐行追加） | process_data |

外部可靠输出文件行数感知进度。


## qinglong
```python
HOSTS = ["rm51798.eos.grid.sina.com.cn"]
PORTS = [51798]
REDIS_KEY_PREFIX = "blog_pre_cache"
mid_key = f"mid:q1:{mid}"
```

用户互动数据，mid_key由```f"mid:q:{mid}"```修改为```f"mid:q1:{mid}"```
