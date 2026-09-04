#! -*- encoding: utf-8 -*-

import os
import time
import json
import base64
import aiohttp
import asyncio
from PIL import Image
from io import BytesIO


IMG_BASE_URL = "http://bj.service.t.sinaimg.cn/middle/"


def image_bytes_to_standard_jpeg_data_url(img_bytes: bytes) -> str:
    """
    将图片 bytes 统一转成标准 JPEG data URL。
    避免原始 jpg/png/webp 等格式在模型侧解析失败。
    """
    try:
        img = Image.open(BytesIO(img_bytes))
        img.load()
    except Exception as e:
        preview = img_bytes[:200].decode("utf-8", errors="ignore")
        raise ValueError(f"图片内容无法识别，可能不是有效图片。error={repr(e)}, preview={preview}") from e

    if img.mode != "RGB":
        img = img.convert("RGB")

    output = BytesIO()
    img.save(output, format="JPEG", quality=95)

    jpeg_bytes = output.getvalue()
    img_b64 = base64.b64encode(jpeg_bytes).decode("utf-8")

    return f"data:image/jpeg;base64,{img_b64}"


def local_image_to_data_url(image_path: str) -> str:
    """
    本地图片 -> 标准 JPEG data URL
    """
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    return image_bytes_to_standard_jpeg_data_url(img_bytes)


async def url_image_to_data_url(session: aiohttp.ClientSession, url: str) -> str:
    """
    URL 图片 -> 下载 bytes -> 标准 JPEG data URL
    """
    async with session.get(url) as resp:
        img_bytes = await resp.read()

        if resp.status >= 400:
            preview = img_bytes[:300].decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"图片下载失败，status={resp.status}, url={url}, response_preview={preview}"
            )

        content_type = resp.headers.get("Content-Type", "").lower()

        if not (
            content_type.startswith("image/")
            or content_type in ["application/octet-stream", "binary/octet-stream"]
        ):
            preview = img_bytes[:500].decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"下载内容不是图片，Content-Type={content_type}, url={url}, "
                f"preview={preview[:200]}..."
            )

    return image_bytes_to_standard_jpeg_data_url(img_bytes)


async def pid_to_base64(session: aiohttp.ClientSession, pid: str):
    url = f"{IMG_BASE_URL}{pid}"

    async with session.get(url) as resp:
        resp.raise_for_status()
        img_bytes = await resp.read()

    img_b64 = base64.b64encode(img_bytes).decode("utf-8")

    return f"data:image/jpeg;base64,{img_b64}"


def looks_like_local_image_path(value: str) -> bool:
    """
    判断是否像本地图片路径，避免 test.jpg 不存在时被误当成 pid。
    """
    image_exts = (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".bmp",
        ".gif",
        ".tif",
        ".tiff",
    )

    lower_value = value.lower()

    return (
        lower_value.endswith(image_exts)
        or "/" in value
        or "\\" in value
    )


async def parse_image_to_data_url(session: aiohttp.ClientSession, image_or_pid: str) -> str:
    """
    支持本地图片路径、图片 URL、data URL、pid。
    """
    if image_or_pid.startswith("data:image/"):
        return image_or_pid

    if os.path.exists(image_or_pid):
        return local_image_to_data_url(image_or_pid)

    if image_or_pid.startswith("http://") or image_or_pid.startswith("https://"):
        return await url_image_to_data_url(session, image_or_pid)

    if looks_like_local_image_path(image_or_pid):
        raise FileNotFoundError(
            f"本地图片不存在：{image_or_pid}，请检查运行目录或使用绝对路径。"
        )

    return await pid_to_base64(session, image_or_pid)