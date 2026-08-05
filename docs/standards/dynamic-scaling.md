# 动态扩容（高峰期防爆）

## 核心闭环

```
服务 /metrics（请求量/错误率/延迟） ──抓取──> 自动扩缩器（策略判定） ──执行──> docker compose --scale
      ↑                                                                            │
      └──────────── 新副本启动后向注册中心心跳登记，网关动态发现并接入流量 ←────────┘
```

「能测 → 能判 → 能执行 → 能感知」，四环缺一不可。

## 1. 度量（能测）

- 内核 `kernel/metrics.py`：Prometheus 格式 `/metrics`（请求量 / 错误率 / 延迟直方图 / 在途请求），所有服务自动暴露；
- 扩缩器据此计算**每实例 RPS** 与错误率。

## 2. 策略（能判）

`services/autoscaler/autoscaler/policy.py`（纯函数，可单测）：

| 参数 | 默认 | 说明 |
|---|---|---|
| SCALE_UP_RPS | 20 | 每实例 RPS 高于此值触发扩容 |
| SCALE_DOWN_RPS | 5 | 每实例 RPS 低于此值触发缩容 |
| ERROR_RATE_THRESHOLD | 0.05 | 错误率超阈值也触发扩容 |
| SUSTAIN_UP / SUSTAIN_DOWN | 3 / 6 | 连续 N 个周期确认，防抖动 |
| COOLDOWN_SECONDS | 60 | 扩/缩容后冷却，防止振荡 |
| MIN_REPLICAS / MAX_REPLICAS | 1 / 6 | **防爆硬边界**：即使再高负载也封顶，再低也保底 |

## 3. 执行（能执行）

- `services/autoscaler/autoscaler/scaler.py`：
  - `ComposeScaler`：执行 `docker compose up -d --scale <service>=<N>`（宿主模式，需挂 docker.sock）；
  - `NoopScaler`（DRY_RUN=true）：只记录决策不执行，用于演练/灰度。
- **重要**：被自动扩缩的服务在编排中**不暴露宿主机端口**（`ports: []`），否则 `--scale` 多副本会抢占同一宿主端口（实测踩坑：Bind port already allocated）。服务间通过 Docker DNS 内部访问。

## 4. 感知（能感知新副本）

- 内核 `kernel/registry.py`：服务注册中心（Redis 心跳，TTL 过期自动下线）；
- 服务实例启动即注册（`REGISTRY_URL` + `INSTANCE_URL`），心跳续期，下线注销；
- 网关 `UpstreamBalancer.refresh()` 周期性从注册中心刷新实例池（`DISCOVERY_SERVICE`），**新副本自动接入、下线自动摘除**。

## 5. 编排接线（deploy/docker-compose.prod.yml）

- `service-template`：`ports: []`（可 --scale）、`REGISTRY_URL`、`INSTANCE_URL`；
- `gateway`：`REGISTRY_URL` + `DISCOVERY_SERVICE=service-template`；
- `autoscaler`：默认 `DRY_RUN=true`；生产置 false 并挂载 `/var/run/docker.sock` 与 compose 目录。

## 6. 验证（实测）

- 压测 500 请求经 Nginx → 3 网关 → 3 服务，全部 201，**服务端未被打爆**；
- 负载升高 → 扩缩器连续 2 周期确认 → `UP`（副本 2→3→4），冷却期防抖，负载回落自动恢复；
- 真实执行 `--scale service-template=3`：容器 3→5 个全部 healthy，网关经 Nginx 路由 201；
- 注册中心 Redis 中 3 个实例（service-template / -2 / -3），网关动态发现。

## 7. 生产建议

- 单机 Compose：autoscaler 宿主模式（DRY_RUN=false + docker.sock）；
- 多机/K8s：本套件自动扩缩器策略可直接移植为 K8s HPA 自定义指标（prometheus-adapter）；
- 扩缩目标优先选**无状态服务**（网关/业务副本）；有状态（PG）走读写分离扩容从库。