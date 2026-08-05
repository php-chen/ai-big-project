from __future__ import annotations

from kernel.config import Settings


class GatewaySettings(Settings):
    service_name: str = "gateway"
    # 单个上游（向后兼容）
    upstream_service_url: str = "http://localhost:8100"
    # 多个上游实例（逗号分隔，优先于 upstream_service_url）
    upstream_service_urls: str = ""
    upstream_timeout: float = 10.0
    dev_token: str = "dev-token"

    @property
    def upstream_list(self) -> list[str]:
        urls = [u.strip() for u in self.upstream_service_urls.split(",") if u.strip()]
        return urls or [self.upstream_service_url]