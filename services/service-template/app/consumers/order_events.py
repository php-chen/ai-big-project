"""订阅 order.created.v1 的示例（Read Model，定律2 例外条款）。

注意：本文件仅为示例，默认不启用；启用时在 app.main 的 lifespan 中：
    consumer = EventConsumer(bus, idem_store)
    await consumer.subscribe("order.created.v1", handle_order_created)
"""
from __future__ import annotations

import logging

from contract_sdk.events import EventEnvelope

logger = logging.getLogger(__name__)


async def handle_order_created(envelope: EventEnvelope) -> None:
    # 此处可把订单摘要写入本服务拥有的只读表（派生读模型）
    logger.info(
        "收到订单事件 %s/%s",
        envelope.event_name,
        envelope.aggregate_id,
    )