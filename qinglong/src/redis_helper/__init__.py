from src.redis_helper.base import RedisClusterClient


def __getattr__(name):
    """延迟导入，避免包初始化时子模块提前注册到 sys.modules 触发 RuntimeWarning"""
    _lazy_imports = {
        "get_blog_video_summary": "src.redis_helper.blog_video_summary",
        "get_comment_summary": "src.redis_helper.comment_summary",
        "get_pid_analysis_summary": "src.redis_helper.pid_analysis_summary",
        "get_mid_hot_query": "src.redis_helper.mid_hot_query",
    }
    if name in _lazy_imports:
        import importlib
        module = importlib.import_module(_lazy_imports[name])
        return getattr(module, name)
    raise AttributeError(f"module 'src.redis_helper' has no attribute {name!r}")


__all__ = [
    "RedisClusterClient",
    "get_blog_video_summary",
    "get_comment_summary",
    "get_pid_analysis_summary",
    "get_mid_hot_query",
]
