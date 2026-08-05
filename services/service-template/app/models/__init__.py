"""领域模型：本服务拥有的全部表（数据主权：只在这里定义自己的表）。"""
from .user import User

__all__ = ["User"]