# 资源监控（宿主机 / 容器 / 应用三层）

## 架构

```
node-exporter(9100) ─┐
cAdvisor(8080)       ├─> Prometheus(:9090) ──> Grafana(:3000)
gateway×3 /metrics   │      │
service-template×3   │      └─> 告警规则（Alertmanager 可扩展）
autoscaler /metrics  ┘
```

| 数据源 | 采集内容 | 采集器 |
|---|---|---|
| 宿主机 | CPU / 内存 / 磁盘 / 网络 | node-exporter |
| 容器 | 每容器 CPU / 内存 / 网络吞吐 | cAdvisor |
| 应用 | QPS / 5xx / P95 延迟 / 在途请求 / Outbox 积压 | kernel `/metrics` |

## 应用指标（内核自动暴露）

所有服务经 `kernel/metrics.py` 暴露 `/metrics`（Prometheus 格式）：
- `http_requests_total{service,method,path,status}`（路径归一化，防基数爆炸）
- `http_request_duration_seconds`（直方图 -> P95）
- `http_requests_in_flight`
- `outbox_pending_total{service}`（Outbox 队列深度，定律4 关键资源，由 Relay 周期性上报）

## 告警规则（deploy/monitoring/alerting-rules.yml）

| 告警 | 条件 | 严重度 |
|---|---|---|
| ServiceDown | `up == 0` 持续 2m | critical |
| HighHostCPU / HighHostMemory | > 85% 持续 5m | warning |
| HighContainerCPU / HighContainerMemory | 容器 > 80% / 85% 持续 5m | warning |
| HighErrorRate | 5xx 占比 > 5% 持续 5m | warning |
| OutboxBacklogHigh | `outbox_pending_total > 100` 持续 5m | warning |
| TooManyInflight | 在途请求 > 200 持续 2m | warning |

## Grafana 大盘（自动供给）

`deploy/monitoring/grafana/` 预置数据源与大盘 `resource-overview.json`：
- 宿主机 CPU/内存；容器 CPU/内存/网络；QPS/错误率/P95/在途/Outbox 积压。

## 启用

```powershell
# 启动监控栈（默认关闭，避免资源占用）
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod \
  --profile monitoring up -d

# 入口
#   Prometheus: http://localhost:9090/targets
#   Grafana:    http://localhost:3000  (admin / GRAFANA_ADMIN_PASSWORD)
```

## 与动态扩容联动

- 监控栈与自动扩缩器共用 `/metrics`：监控负责“看”，扩缩器负责“扩”；
- 告警可通知运维人工介入；扩缩器按策略自动吸收流量高峰（见 dynamic-scaling.md）。

## 生产建议

- Prometheus 数据落盘（`promdata` 卷），建议接对象存储/长期存储（Thanos）；
- 告警接入 Alertmanager -> 钉钉/飞书/Slack；
- 多集群采集用 federation 或 Prometheus Agent。