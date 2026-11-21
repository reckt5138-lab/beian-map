"""青鸾备案项目地图 V2.1 —— 应用包。

模块边界：
    app.core        配置、路径、日志、异常
    app.crawler     采集（现有 crawler.py 保留原位，逐步迁移）
    app.data        校验、原子写入、JSON 导出
    app.map         地图构建
    app.security    数据脱敏、凭证处理
    app.main        统一命令行入口

V2 → V2.1 采用渐进式重构：现有可运行的入口（app/crawler.py、app/build_map_html.py 等）
全部保留可用，新能力以新增模块方式接入，避免一次性搬迁破坏 158 列采集链路。
"""

__version__ = "2.1.0"
__all__ = ["__version__"]
