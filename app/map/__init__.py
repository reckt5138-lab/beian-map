"""地图模块：构建、脱敏发布、产物自检。

注意：为了不与子模块 app.map.build 同名冲突，这里导出的是 build_page（函数），
子模块本身用 `import app.map.build` 或 `from app.map import build` 之后取 `.build` 会有歧义，
所以内部统一用 `from app.map import build_page`。
"""

from .build import build as build_page
from .build import copy_to_dist, verify

__all__ = ["build_page", "verify", "copy_to_dist"]
