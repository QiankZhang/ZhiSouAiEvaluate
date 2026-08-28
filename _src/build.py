#!/usr/bin/env python3
# 重新构建 /opt/zhisou-guide/index.html：把 images/*.jpg 内联进 guide.src.html
import base64, re, pathlib
here = pathlib.Path(__file__).parent
src = (here / "guide.src.html").read_text()
imgdir = here / "images"
def repl(m):
    data = (imgdir / m.group(1)).read_bytes()
    return f'src="data:image/jpeg;base64,{base64.b64encode(data).decode()}"'
body = re.sub(r'src="assets/([^"]+)"', repl, src)
body = body.replace('<div class="page">', '</head>\n<body>\n<div class="page">', 1)
doc = '<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n' + body.rstrip() + '\n</body>\n</html>\n'
(here.parent / "index.html").write_text(doc)
print("wrote", here.parent / "index.html", round(len(doc)/1024), "KB")
