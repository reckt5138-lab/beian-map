"""青鸾备案项目地图 V3.0 —— 应用包。

模块边界：
    app.core        配置、路径、日志、异常
    app.crawler     采集（登录、分页、详情，输出完整矩阵 JSON）
    app.matrix_parse 矩阵解析与坐标补全
    app.map_payload 矩阵 → payload、原子写入
    app.data        校验、原子写入、JSON 导出（脱敏白名单）
    app.map         页面模板 → index.html，发布目录
    app.security    数据脱敏、凭证处理
    app.main        统一命令行入口

V3.0 的边界：页面只读同目录 ./data.json；后端只负责「抓取 → 脱敏 → 校验 → 生成 dist」。
"""

__version__ = "3.0.0"
__all__ = ["__version__"]
