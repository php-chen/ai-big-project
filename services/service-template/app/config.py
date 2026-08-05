"""服务级配置：继承内核 Settings，只增加本服务特有配置。"""
from __future__ import annotations

from kernel.config import Settings


class ServiceSettings(Settings):
    service_name: str = "service-template"

    # 数据主权（定律2）：本服务只拥有 users 表，严禁访问其他服务的数据表
    default_page_size: int = 20

    @property
    def replica_database_url_list(self) -> list[str]:
        """多读副本列表（REPLICA_DATABASE_URLS 逗号分隔）。"""
        return [u.strip() for u in self.replica_database_urls.split(",") if u.strip()]