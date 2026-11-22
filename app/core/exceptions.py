"""自定义异常：统一的类型便于上层给出中文提示，而不是抛一大段 traceback。"""


class JbufaError(Exception):
    """项目内所有可预期错误的基类。"""

    exit_code = 1

    def __init__(self, message, hint=""):
        super().__init__(message)
        self.message = message
        self.hint = hint

    def as_text(self):
        if self.hint:
            return "%s\n提示：%s" % (self.message, self.hint)
        return self.message


class ConfigError(JbufaError):
    """配置缺失或格式错误。"""


class LoginError(JbufaError):
    """登录失败：账号密码错、接口改版、网络不可达。"""

    exit_code = 2

    def __init__(self, message, hint="检查 JUFA_USERNAME / JUFA_PASSWORD，或青鸾站点是否改版"):
        super().__init__(message, hint)


class CrawlError(JbufaError):
    """采集过程中断（分页未完成、详情失败过多等）。"""

    exit_code = 3


class DataValidationError(JbufaError):
    """数据校验不通过，禁止发布（保留上一版）。"""

    exit_code = 4


class PublishBlocked(JbufaError):
    """安全检查未通过，禁止发布。"""

    exit_code = 5
