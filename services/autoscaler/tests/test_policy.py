"""扩缩容策略测试：持续区间 / 冷却 / min-max 边界 / 错误率触发。"""
from __future__ import annotations

from autoscaler.config import AutoscalerSettings
from autoscaler.policy import PolicyState, decide


def make_settings(**kw) -> AutoscalerSettings:
    return AutoscalerSettings(app_env="test", log_level="ERROR", **kw)


def test_scale_up_after_sustain():
    s = make_settings(scale_up_rps=20, scale_down_rps=5, sustain_up=2, sustain_down=4, cooldown_seconds=60)
    state = PolicyState()
    d1 = decide(settings=s, state=state, current_replicas=2, rps_per_instance=30, error_rate=0.0, now=100.0)
    assert d1.action == "hold"
    d2 = decide(settings=s, state=state, current_replicas=2, rps_per_instance=30, error_rate=0.0, now=101.0)
    assert d2.action == "up"


def test_scale_down_after_sustain():
    s = make_settings(scale_up_rps=20, scale_down_rps=5, sustain_up=2, sustain_down=3, cooldown_seconds=60)
    state = PolicyState()
    decision = None
    for i in range(3):
        decision = decide(settings=s, state=state, current_replicas=4, rps_per_instance=1.0, error_rate=0.0, now=100.0 + i)
    assert decision is not None and decision.action == "down"


def test_max_replicas_boundary():
    s = make_settings(max_replicas=3, sustain_up=1, cooldown_seconds=60)
    state = PolicyState()
    d = decide(settings=s, state=state, current_replicas=3, rps_per_instance=99, error_rate=0.0, now=100.0)
    assert d.action == "hold"
    assert "上限" in d.reason


def test_min_replicas_boundary():
    s = make_settings(min_replicas=1, sustain_down=1, cooldown_seconds=60)
    state = PolicyState()
    d = decide(settings=s, state=state, current_replicas=1, rps_per_instance=0.0, error_rate=0.0, now=100.0)
    assert d.action == "hold"


def test_cooldown_blocks_then_allows():
    s = make_settings(sustain_up=1, cooldown_seconds=60)
    state = PolicyState()
    d1 = decide(settings=s, state=state, current_replicas=2, rps_per_instance=99, error_rate=0.0, now=10.0)
    assert d1.action == "hold"  # 冷却中
    d2 = decide(settings=s, state=state, current_replicas=2, rps_per_instance=99, error_rate=0.0, now=61.0)
    assert d2.action == "up"


def test_error_rate_triggers_up():
    s = make_settings(error_rate_threshold=0.05, sustain_up=1, cooldown_seconds=0)
    state = PolicyState()
    d = decide(settings=s, state=state, current_replicas=2, rps_per_instance=1.0, error_rate=0.2, now=1.0)
    assert d.action == "up"