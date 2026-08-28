# 操作指南源文件（用于重建 ../index.html）

- `guide.src.html` — 正文 + 内联 CSS/JS，图片以 `assets/xxx.jpg` 占位
- `images/` — 13 张界面截图
- `build.py` — 把 images 内联为 base64，产出仓库根的 `index.html`

## 更新
```bash
cd _src && python3 build.py        # 覆盖 ../index.html
cd .. && git add -A && git commit -m "更新操作指南" && git push
```
GitHub Pages（gh-pages 分支）会自动重新发布，约 1 分钟。

## 线上
https://qiankzhang.github.io/ZhiSouAiEvaluate/  （noindex，不被搜索引擎收录）
