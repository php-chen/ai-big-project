from __future__ import annotations

from kernel.config import Settings


class AutoscalerSettings(Settings):
    service_name: str = "autoscaler"

    # 扩容目标
    target_service: str = "service-template"
    target_urls: str = ""          # 逗号分隔：要抓取指标的实例（至少一个）
    interval_seconds: float = 5.0

    # 策略阈值（每实例）
    scale_up_rps: float = 20.0     # 每实例 RPS 高于此值 -> 扩容
    scale_down_rps: float = 5.0    # 每实例 RPS 低于此值 -> 缩容
    error_rate_threshold: float = 0.05

    # 持续区间与冷却（防抖动）
    sustain_up: int = 3            # 连续 N 个周期满足才扩容
    sustain_down: int = 6
    cooldown_seconds: float = 60.0

    # 副本上下限（防爆的硬边界）
    min_replicas: int = 1
    max_replicas: int = 6

    # 执行
    dry_run: bool = True           # True=只记录决策；False=执行 docker compose --scale
    compose_dir: str = "."
    compose_file: str = "docker-compose.prod.yml"
    compose_env_file: str = ".env.prod"

    @property
    def target_url_list(self) -> list[str]:
        return [u.strip() for u in self.target_urls.split(",") if u.strip()]