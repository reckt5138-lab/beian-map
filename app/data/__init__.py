"""数据层：校验、原子写入、JSON 导出。

注意：本包刻意**不**导出名为 validate / save 的函数，避免和子模块
app.data.validate、app.data.save 同名覆盖（Python 里包属性会遮住子模块）。
"""

from .atomic import atomic_copy, atomic_write_bytes, atomic_write_json, atomic_write_text, backup_file
from .export_json import core, export_public, matrix_to_payload, same_data, save_payload
from .validate import load_previous, validate_payload

__all__ = [
    "atomic_write_bytes", "atomic_write_json", "atomic_write_text", "atomic_copy", "backup_file",
    "validate_payload", "load_previous",
    "matrix_to_payload", "core", "same_data", "save_payload", "export_public",
]
