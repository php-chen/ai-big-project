"""统一配置加载（方向一：环境变量命名标准化）。

所有微服务继承 Settings，只从环境变量读取配置，禁止硬编码连接信息。
命名规范：全小写下划线；连接串统一 <类型>_URL。
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 运行环境 ----
    app_env: str = "development"          # development | staging | production
    app_name: str = "ai-big-project"
    service_name: str = "service"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    # ---- 数据源（读写分离：主库写，从库读）----
    database_url: str | None = None
    replica_database_url: str | None = None
    replica_database_urls: str = ""   # 逗号分隔多个读副本，优先于 replica_database_url
    redis_url: str | None = None
    amqp_url: str | None = None

    # ---- 安全（定律3）----
    trust_proxy_headers: bool = False
    jwt_issuer: str | None = None
    jwt_audience: str | None = None

    # ---- 幂等（定律4）----
    idempotency_ttl_seconds: int = 3600

    # ---- Outbox（定律4）----
    outbox_poll_interval_seconds: float = 2.0
    outbox_batch_size: int = 100

    # ---- 可观测性（定律5）----
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str | None = None

    # ---- 服务注册/发现（动态扩容）----
    registry_url: str | None = None      # 服务注册中心（Redis）；空则进程内降级
    instance_url: str = ""               # 本实例对外可达地址（注册用，如 http://host:8100）
    service_registry_ttl_seconds: int = 30
    discovery_service: str = ""          # 网关要动态发现的服务名；空则关闭发现

    # ---- 日志（定律5）----
    log_json: bool = True
    log_access: bool = True
    log_slow_query_ms: int = 0   # >0 时开启慢查询日志（毫秒阈值）

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings(**overrides) -> Settings:
    """进程级单例配置；测试中可传入 overrides 覆盖字段。"""
    return Settings(**overrides)