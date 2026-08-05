"""事件消费者（定律4：订阅其他服务的事件，at-least-once + 幂等）。

示例：本服务可订阅订单服务发布的 order.created.v1 维护派生读模型（Read Model）。
实际消费者请在 lifespan 中通过 EventConsumer 订阅。
"""