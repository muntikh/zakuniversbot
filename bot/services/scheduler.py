from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from bot.config import settings
from bot.db.database import AsyncSessionLocal
from bot.db.crud import set_order_status
from bot.db.models import Order, OrderStatus
from sqlalchemy import select

scheduler = AsyncIOScheduler(timezone="Asia/Tehran")


async def _expire_pending_orders() -> None:
    """
    Every 5 minutes: expire orders that have been PENDING or AWAITING_RECEIPT
    for longer than ORDER_EXPIRY_MINUTES without a receipt being submitted.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=settings.order_expiry_minutes)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Order).where(
                Order.status.in_([
                    OrderStatus.PENDING,
                    OrderStatus.AWAITING_RECEIPT,
                ]),
                Order.created_at < cutoff,
            )
        )
        orders = result.scalars().all()
        for order in orders:
            logger.info(f"Auto-expiring order {order.id} (created {order.created_at})")
            await set_order_status(session, order.id, OrderStatus.EXPIRED)


async def _refresh_panel_token() -> None:
    """Every 20 hours: refresh the PasarGuard JWT before it expires."""
    from bot.services.pasarguard import panel  # noqa: PLC0415
    await panel.refresh_token()


async def _sync_panel_data() -> None:
    """Every 10 minutes: reconcile all users and traffic from PasarGuard panel into DB."""
    from bot.services.stats import sync_panel_subscriptions_fast  # noqa: PLC0415
    async with AsyncSessionLocal() as session:
        await sync_panel_subscriptions_fast(session)


def setup_scheduler() -> None:
    scheduler.add_job(
        _expire_pending_orders,
        trigger="interval",
        minutes=5,
        id="expire_pending_orders",
        replace_existing=True,
    )
    scheduler.add_job(
        _sync_panel_data,
        trigger="interval",
        minutes=10,
        id="sync_panel_data",
        replace_existing=True,
    )
    scheduler.add_job(
        _refresh_panel_token,
        trigger="interval",
        hours=20,
        id="refresh_panel_token",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started")
