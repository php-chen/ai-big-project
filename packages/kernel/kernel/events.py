"""事件发布/消费基座（定律4：本地事务 + 领域事件；定律5：消息头透传 trace）。

- EventPublisher：统一发布接口；
- LocalEventBus：进程内总线（开发/测试，不跨进程）；
- RabbitEventBus：RabbitMQ 主题交换机实现（生产）；
- EventConsumer：消费基座，at-least-once + 幂等去重。
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from contract_sdk.events import EventEnvelope, TraceContext

from .context import get_trace_id

logger = logging.getLogger(__name__)

EventHandler = Callable[[EventEnvelope], Awaitable[None]]


class EventPublisher(Protocol):
    async def publish(self, envelope: EventEnvelope) -> None: ...


class LocalEventBus:
    """进程内事件总线：订阅者按事件名路由；用于开发/测试与 Outbox relay。"""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_name, []).append(handler)

    async def publish(self, envelope: EventEnvelope) -> None:
        for handler in self._handlers.get(envelope.event_name, []):
            await handler(envelope)


class RabbitEventBus:
    """RabbitMQ 实现：主题交换机 domain-events，routing key = event_name。

    生产环境使用；开发/测试无 RabbitMQ 时用 LocalEventBus。
    """

    EXCHANGE = "domain-events"
    EXCHANGE_TYPE = "topic"

    def __init__(self, amqp_url: str) -> None:
        self._url = amqp_url
        self._connection: Any = None
        self._channel: Any = None
        self._exchange: Any = None

    async def connect(self) -> None:
        import aio_pika

        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            self.EXCHANGE, self.EXCHANGE_TYPE, durable=True
        )

    async def publish(self, envelope: EventEnvelope) -> None:
        import aio_pika

        if self._exchange is None:
            await self.connect()
        headers: dict[str, str] = {}
        if envelope.trace:
            headers["traceparent"] = envelope.trace.traceparent
        message = aio_pika.Message(
            body=envelope.model_dump_json().encode("utf-8"),
            content_type="application/json",
            message_id=envelope.event_id,
            headers=headers,
            timestamp=envelope.occurred_at,
        )
        await self._exchange.publish(message, routing_key=envelope.event_name)

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()


def build_event_bus(amqp_url: str | None) -> EventPublisher:
    """按配置构建事件总线（定律4 真实落地）：
    配置 AMQP_URL -> RabbitMQ（生产，跨服务）；否则进程内 LocalEventBus（开发/测试）。
    """
    if amqp_url:
        return RabbitEventBus(amqp_url)
    logger.warning("未配置 AMQP_URL，使用进程内 LocalEventBus（仅限开发/测试；生产必须 RabbitMQ）")
    return LocalEventBus()

def envelope_trace_from_context() -> TraceContext | None:
    """从当前 contextvars 构造事件 trace（Outbox 落库时记录，relay 投递时透传）。"""
    trace_id = get_trace_id()
    if not trace_id:
        return None
    return TraceContext(trace_id=trace_id, span_id="0" * 16)


class EventConsumer:
    """事件消费基座：at-least-once + 幂等去重（用 IdempotencyStore 记 event_id）。

    用法：consumer = EventConsumer(bus, idem_store); await consumer.subscribe("user.created.v1", handler)
    """

    def __init__(self, bus: LocalEventBus | RabbitEventBus, idem_store: Any = None) -> None:
        self._bus = bus
        self._idem_store = idem_store

    async def subscribe(self, event_name: str, handler: EventHandler) -> None:
        async def guarded(envelope: EventEnvelope) -> None:
            if self._idem_store is not None:
                key = f"evt:{event_name}:{envelope.event_id}"
                if not await self._idem_store.acquire(key, 86400):
                    logger.info("重复事件已跳过: %s/%s", event_name, envelope.event_id)
                    return
            try:
                await handler(envelope)
            except Exception:
                logger.exception("事件处理失败: %s/%s", event_name, envelope.event_id)
                raise
            finally:
                if self._idem_store is not None:
                    await self._idem_store.put(key, "done", 86400)

        if isinstance(self._bus, LocalEventBus):
            self._bus.subscribe(event_name, guarded)
            return

        # RabbitMQ：先确保连接，再声明队列绑定主题
        import aio_pika

        if self._bus._channel is None:
            await self._bus.connect()
        channel = self._bus._channel
        queue = await channel.declare_queue(event_name, durable=True)
        await queue.bind(self._bus._exchange, routing_key=event_name)

        async def on_message(message: aio_pika.IncomingMessage) -> None:
            async with message.process():
                envelope = EventEnvelope.model_validate_json(message.body)
                await guarded(envelope)

        await queue.consume(on_message)