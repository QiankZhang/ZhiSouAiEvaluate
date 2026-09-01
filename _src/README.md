# 操作指南源文件（用于重建 ../index.html）

- `guide.src.html` — 正文 + 内联 CSS/JS，图片以 `assets/xxx.jpg` 占位
- `images/` — 界面截图（1500px 宽 JPEG）
- `build.py` — 把 images 内联为 base64，产出仓库根的自包含单文件 `index.html`

## 更新
```bash
cd _src && python3 build.py        # 覆盖 ../index.html
cd .. && git add -A && git commit -m "更新操作指南" && git push origin gh-pages
```
GitHub Pages（gh-pages 分支）约 1 分钟后自动重新发布。

## 线上
https://qiankzhang.github.io/ZhiSouAiEvaluate/  （noindex，不被搜索引擎收录）

## 截图
用 puppeteer-core 驱动已登录的 dev 服务器批量截取（见历史会话脚本 shoot.js）。
标注工作台正文为智搜内部测试语料，截图时对 `.annotate-query / .gsb-col-body / .unit-text` 注入 blur。
