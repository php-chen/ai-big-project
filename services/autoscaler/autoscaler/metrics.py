"""Prometheus 文本指标解析（从服务 /metrics 抓取）。"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ServiceSample:
    requests_total: float = 0.0
    error_total: float = 0.0


def parse_prometheus_text(text: str) -> dict[str, dict[str, float]]:
    """解析 Prometheus 文本格式 -> {metric_name: {label_key: value}}。

    label_key 形如 'service="x",method="GET",...'；无标签时为 ""。
    """
    result: dict[str, dict[str, float]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "{" in line:
            name, rest = line.split("{", 1)
            labels_part, value = rest.rsplit("}", 1)
        else:
            name, value = line.rsplit(" ", 1)
            labels_part = ""
        try:
            result.setdefault(name.strip(), {})[labels_part.strip()] = float(value.strip())
        except ValueError:
            continue
    return result


def extract_sample(parsed: dict[str, dict[str, float]], service: str) -> ServiceSample:
    """聚合某服务的请求总数与错误数（status>=500）。"""
    counters = parsed.get("http_requests_total", {})
    sample = ServiceSample()
    service_label = f'service="{service}"'
    for label_key, value in counters.items():
        if service_label not in label_key:
            continue
        sample.requests_total += value
        if re.search(r'status="5\d\d"', label_key):
            sample.error_total += value
    return sample


def compute_rps(now: float, prev: ServiceSample | None, curr: ServiceSample, window_seconds: float) -> tuple[float, float]:
    """返回 (请求 RPS, 错误率)。首个样本返回 0。"""
    if prev is None:
        return 0.0, 0.0
    total_delta = curr.requests_total - prev.requests_total
    error_delta = curr.error_total - prev.error_total
    if window_seconds <= 0 or total_delta < 0:
        return 0.0, 0.0
    rps = total_delta / window_seconds
    error_rate = error_delta / total_delta if total_delta > 0 else 0.0
    return rps, min(error_rate, 1.0)