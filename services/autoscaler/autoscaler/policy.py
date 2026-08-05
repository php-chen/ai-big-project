"""扩缩容策略引擎（纯函数，可单元测试）。

- 每实例 RPS 高于 scale_up_rps 或错误率高于阈值 -> 连续 sustain_up 个周期后扩容；
- 每实例 RPS 低于 scale_down_rps -> 连续 sustain_down 个周期后缩容；
- 冷却期防抖；min/max 硬边界（防爆）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .config import AutoscalerSettings


@dataclass
class Decision:
    action: str  # up / down / hold
    reason: str


@dataclass
class PolicyState:
    up_streak: int = 0
    down_streak: int = 0
    last_action_at: float = 0.0

    def reset(self) -> None:
        self.up_streak = 0
        self.down_streak = 0


def decide(
    *,
    settings: AutoscalerSettings,
    state: PolicyState,
    current_replicas: int,
    rps_per_instance: float,
    error_rate: float,
    now: float | None = None,
) -> Decision:
    now = now if now is not None else time.monotonic()
    cooldown_left = settings.cooldown_seconds - (now - state.last_action_at)
    if cooldown_left > 0:
        return Decision("hold", f"冷却中，剩余 {cooldown_left:.0f}s")

    if rps_per_instance > settings.scale_up_rps or error_rate > settings.error_rate_threshold:
        state.down_streak = 0
        if current_replicas >= settings.max_replicas:
            state.up_streak = 0
            return Decision("hold", f"已达副本上限 {settings.max_replicas}（防爆边界）")
        state.up_streak += 1
        if state.up_streak >= settings.sustain_up:
            state.up_streak = 0
            state.last_action_at = now
            return Decision("up", f"负载过高（rps/实例={rps_per_instance:.1f}, 错误率={error_rate:.2%}），扩容")
        return Decision("hold", f"负载偏高，待确认 {state.up_streak}/{settings.sustain_up}")

    if rps_per_instance < settings.scale_down_rps:
        state.up_streak = 0
        if current_replicas <= settings.min_replicas:
            state.down_streak = 0
            return Decision("hold", f"已达副本下限 {settings.min_replicas}")
        state.down_streak += 1
        if state.down_streak >= settings.sustain_down:
            state.down_streak = 0
            state.last_action_at = now
            return Decision("down", f"负载低（rps/实例={rps_per_instance:.1f}），缩容")
        return Decision("hold", f"负载偏低，待确认 {state.down_streak}/{settings.sustain_down}")

    state.reset()
    return Decision("hold", f"负载正常（rps/实例={rps_per_instance:.1f}）")