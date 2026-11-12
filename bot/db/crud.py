from __future__ import annotations

import random
import string
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    BotSetting,
    Discount,
    Order,
    OrderStatus,
    Plan,
    Subscription,
    Transaction,
    TransactionStatus,
    TransactionType,
    User,
)


# ─────────────────────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────────────────────

async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str],
    full_name: str,
) -> User:
    user = await session.get(User, telegram_id)
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            referral_code=_gen_referral_code(),
        )
        session.add(user)
    else:
        user.username = username
        user.full_name = full_name
        user.last_seen_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def get_user(session: AsyncSession, telegram_id: int) -> Optional[User]:
    return await session.get(User, telegram_id)


async def set_user_blocked(
    session: AsyncSession, telegram_id: int, blocked: bool
) -> None:
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(is_blocked=blocked)
    )
    await session.commit()


def _gen_referral_code(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


# ─────────────────────────────────────────────────────────────
# Plans
# ─────────────────────────────────────────────────────────────

async def get_active_plans(session: AsyncSession) -> list[Plan]:
    result = await session.execute(
        select(Plan)
        .where(Plan.is_active.is_(True), Plan.show_in_menu.is_(True))
        .order_by(Plan.order_index, Plan.duration_days, Plan.data_gb)
    )
    return list(result.scalars().all())


async def get_plan(session: AsyncSession, plan_id: int) -> Optional[Plan]:
    return await session.get(Plan, plan_id)


async def get_plans_by_duration(
    session: AsyncSession, duration_days: int
) -> list[Plan]:
    result = await session.execute(
        select(Plan)
        .where(
            Plan.is_active.is_(True),
            Plan.show_in_menu.is_(True),
            Plan.duration_days == duration_days,
        )
        .order_by(Plan.order_index, Plan.price_toman)
    )
    return list(result.scalars().all())


# ─────────────────────────────────────────────────────────────
# Orders
# ─────────────────────────────────────────────────────────────

def _gen_order_id() -> str:
    suffix = "".join(random.choices(string.digits, k=5))
    return f"ORD-{suffix}"


async def create_order(
    session: AsyncSession,
    user_id: int,
    plan_id: int,
    amount_toman: int,
    discount_applied: int = 0,
    expires_at: Optional[datetime] = None,
    custom_config_name: Optional[str] = None,
) -> Order:
    order_id = _gen_order_id()
    # Ensure unique
    while await session.get(Order, order_id):
        order_id = _gen_order_id()

    order = Order(
        id=order_id,
        user_id=user_id,
        plan_id=plan_id,
        amount_toman=amount_toman,
        discount_applied=discount_applied,
        expires_at=expires_at,
        custom_config_name=custom_config_name,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def get_order(session: AsyncSession, order_id: str) -> Optional[Order]:
    return await session.get(Order, order_id)


async def get_pending_order_for_user(
    session: AsyncSession, user_id: int
) -> Optional[Order]:
    """Returns active non-terminal order for a user, if any."""
    result = await session.execute(
        select(Order)
        .where(
            Order.user_id == user_id,
            Order.status.in_([
                OrderStatus.PENDING,
                OrderStatus.AWAITING_RECEIPT,
                OrderStatus.RECEIPT_SENT,
            ]),
        )
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def atomic_confirm_order(
    session: AsyncSession,
    order_id: str,
    admin_id: int,
) -> tuple[bool, Optional[int]]:
    """
    Atomically moves order from RECEIPT_SENT → CONFIRMED.
    Credits user wallet balance and logs a Transaction.
    Returns (True, new_balance) if this admin confirmed first, else (False, None).
    """
    order = await session.get(Order, order_id)
    if not order or order.status != OrderStatus.RECEIPT_SENT:
        return False, None

    order.status = OrderStatus.CONFIRMED
    order.confirmed_by_admin_id = admin_id
    order.confirmed_at = datetime.utcnow()

    # Credit the user's wallet (ensure user row exists)
    user = await session.get(User, order.user_id)
    if not user:
        user = User(
            telegram_id=order.user_id,
            username=None,
            full_name=f"کاربر {order.user_id}",
            balance_toman=0,
            referral_code=_gen_referral_code(),
        )
        session.add(user)
        await session.flush()

    user.balance_toman += order.amount_toman
    new_balance = user.balance_toman

    # Record transaction in transactions table
    txn_id = _gen_transaction_id()
    while await session.get(Transaction, txn_id):
        txn_id = _gen_transaction_id()

    txn = Transaction(
        id=txn_id,
        user_id=order.user_id,
        amount_toman=order.amount_toman,
        balance_after=new_balance,
        transaction_type=TransactionType.DEPOSIT,
        status=TransactionStatus.SUCCESS,
        description=f"شارژ حساب / تایید سفارش {order.id}",
        receipt_file_id=order.receipt_file_id,
        verified_by_admin_id=admin_id,
    )
    session.add(txn)

    await session.commit()
    return True, new_balance


async def set_order_status(
    session: AsyncSession,
    order_id: str,
    status: OrderStatus,
) -> None:
    await session.execute(
        update(Order).where(Order.id == order_id).values(status=status)
    )
    await session.commit()


async def set_order_receipt(
    session: AsyncSession, order_id: str, file_id: str, payment_method: str
) -> None:
    await session.execute(
        update(Order)
        .where(Order.id == order_id)
        .values(
            receipt_file_id=file_id,
            payment_method=payment_method,
            status=OrderStatus.RECEIPT_SENT,
        )
    )
    await session.commit()


# ─────────────────────────────────────────────────────────────
# Subscriptions
# ─────────────────────────────────────────────────────────────

async def create_subscription(
    session: AsyncSession,
    user_id: int,
    order_id: str,
    marzban_username: str,
    subscription_url: str,
    expire_timestamp: Optional[datetime],
    data_limit_bytes: int,
) -> Subscription:
    sub = Subscription(
        user_id=user_id,
        order_id=order_id,
        marzban_username=marzban_username,
        subscription_url=subscription_url,
        expire_timestamp=expire_timestamp,
        data_limit_bytes=data_limit_bytes,
    )
    session.add(sub)
    # Mark order as delivered
    await session.execute(
        update(Order)
        .where(Order.id == order_id)
        .values(status=OrderStatus.DELIVERED)
    )
    await session.commit()
    await session.refresh(sub)
    return sub


async def get_user_subscriptions(
    session: AsyncSession, user_id: int
) -> list[Subscription]:
    result = await session.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
    )
    return list(result.scalars().all())


async def get_subscription(
    session: AsyncSession, sub_id: int
) -> Optional[Subscription]:
    return await session.get(Subscription, sub_id)


async def get_subscription_by_username(
    session: AsyncSession, username: str
) -> Optional[Subscription]:
    result = await session.execute(
        select(Subscription).where(Subscription.marzban_username == username)
    )
    return result.scalar_one_or_none()


async def update_subscription_traffic(
    session: AsyncSession, sub_id: int, extra_bytes: int
) -> Optional[Subscription]:
    sub = await session.get(Subscription, sub_id)
    if sub:
        sub.data_limit_bytes += extra_bytes
        await session.commit()
        await session.refresh(sub)
    return sub


async def update_subscription_renew(
    session: AsyncSession, sub_id: int, new_expire: datetime
) -> Optional[Subscription]:
    sub = await session.get(Subscription, sub_id)
    if sub:
        sub.expire_timestamp = new_expire
        sub.used_traffic_bytes = 0
        sub.status = "active"
        await session.commit()
        await session.refresh(sub)
    return sub


# ─────────────────────────────────────────────────────────────
# Discounts
# ─────────────────────────────────────────────────────────────

async def validate_and_use_discount(
    session: AsyncSession, code: str
) -> Optional[Discount]:
    """
    Returns the discount if valid, increments used_count, returns None if invalid.
    """
    result = await session.execute(
        select(Discount).where(
            Discount.code == code,
            Discount.is_active.is_(True),
            Discount.used_count < Discount.max_usage,
        )
    )
    discount = result.scalar_one_or_none()
    if discount is None:
        return None
    if discount.expire_at and discount.expire_at < datetime.utcnow():
        return None
    discount.used_count += 1
    await session.commit()
    return discount


# ─────────────────────────────────────────────────────────────
# Bot Settings
# ─────────────────────────────────────────────────────────────

async def get_setting(
    session: AsyncSession, key: str, default: str = ""
) -> str:
    setting = await session.get(BotSetting, key)
    return setting.value if setting else default


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    setting = await session.get(BotSetting, key)
    if setting:
        setting.value = value
    else:
        session.add(BotSetting(key=key, value=value))
    await session.commit()


# ─────────────────────────────────────────────────────────────
# Wallet & Transactions
# ─────────────────────────────────────────────────────────────

def _gen_transaction_id() -> str:
    suffix = "".join(random.choices(string.digits, k=5))
    return f"TXN-{suffix}"


async def create_deposit_transaction(
    session: AsyncSession,
    user_id: int,
    amount_toman: int,
    receipt_file_id: str,
) -> Transaction:
    txn_id = _gen_transaction_id()
    while await session.get(Transaction, txn_id):
        txn_id = _gen_transaction_id()

    txn = Transaction(
        id=txn_id,
        user_id=user_id,
        amount_toman=amount_toman,
        transaction_type=TransactionType.DEPOSIT,
        status=TransactionStatus.PENDING,
        description=f"درخواست شارژ حساب به مبلغ {amount_toman:,} تومان",
        receipt_file_id=receipt_file_id,
    )
    session.add(txn)
    await session.commit()
    await session.refresh(txn)
    return txn


async def get_transaction(session: AsyncSession, txn_id: str) -> Optional[Transaction]:
    return await session.get(Transaction, txn_id)


async def atomic_confirm_deposit(
    session: AsyncSession,
    txn_id: str,
    admin_id: int,
) -> Optional[int]:
    """
    Atomically updates transaction from PENDING -> SUCCESS
    and adds amount_toman to user.balance_toman.
    Returns new balance if successful, or None if already processed.
    """
    txn = await session.get(Transaction, txn_id)
    if not txn or txn.status != TransactionStatus.PENDING:
        return None

    user = await session.get(User, txn.user_id)
    if not user:
        return None

    # Atomic update
    user.balance_toman += txn.amount_toman
    txn.status = TransactionStatus.SUCCESS
    txn.balance_after = user.balance_toman
    txn.verified_by_admin_id = admin_id

    await session.commit()
    return user.balance_toman


async def reject_deposit(
    session: AsyncSession,
    txn_id: str,
    admin_id: int,
) -> bool:
    txn = await session.get(Transaction, txn_id)
    if not txn or txn.status != TransactionStatus.PENDING:
        return False

    txn.status = TransactionStatus.REJECTED
    txn.verified_by_admin_id = admin_id
    await session.commit()
    return True


async def deduct_wallet_balance(
    session: AsyncSession,
    user_id: int,
    amount_toman: int,
    description: str = "خرید سرویس از کیف پول",
) -> Optional[int]:
    """
    Deducts balance from user's wallet atomically if sufficient.
    Logs a PURCHASE transaction.
    Returns new balance if successful, None if insufficient balance.
    """
    user = await session.get(User, user_id)
    if not user or user.balance_toman < amount_toman:
        return None

    user.balance_toman -= amount_toman

    txn_id = _gen_transaction_id()
    while await session.get(Transaction, txn_id):
        txn_id = _gen_transaction_id()

    txn = Transaction(
        id=txn_id,
        user_id=user_id,
        amount_toman=-amount_toman,
        balance_after=user.balance_toman,
        transaction_type=TransactionType.PURCHASE,
        status=TransactionStatus.SUCCESS,
        description=description,
    )
    session.add(txn)
    await session.commit()
    return user.balance_toman


async def get_user_transactions(
    session: AsyncSession,
    user_id: int,
    limit: int = 10,
) -> list[Transaction]:
    result = await session.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_user_stats(session: AsyncSession, user_id: int) -> dict:
    from sqlalchemy import func
    from bot.db.models import Subscription, Order

    subs_count = await session.scalar(
        select(func.count(Subscription.id)).where(Subscription.user_id == user_id)
    ) or 0

    orders_count = await session.scalar(
        select(func.count(Order.id)).where(
            Order.user_id == user_id,
            Order.status.in_([
                OrderStatus.DELIVERED,
                OrderStatus.PAID_PENDING_PROVISION,
                OrderStatus.CONFIRMED,
            ]),
        )
    ) or 0

    referrals_count = await session.scalar(
        select(func.count(User.telegram_id)).where(User.referred_by == user_id)
    ) or 0

    return {
        "active_subs": subs_count,
        "successful_orders": orders_count,
        "referrals": referrals_count,
    }


async def get_system_stats(session: AsyncSession) -> dict:
    from sqlalchemy import func
    from bot.db.models import User, Subscription, Order, OrderStatus

    total_users = await session.scalar(select(func.count(User.telegram_id))) or 0
    total_subs = await session.scalar(select(func.count(Subscription.id))) or 0
    total_orders = await session.scalar(select(func.count(Order.id))) or 0
    delivered_orders = await session.scalar(
        select(func.count(Order.id)).where(Order.status == OrderStatus.DELIVERED)
    ) or 0
    total_revenue = await session.scalar(
        select(func.sum(Order.amount_toman)).where(Order.status == OrderStatus.DELIVERED)
    ) or 0

    return {
        "total_users": total_users,
        "total_subs": total_subs,
        "total_orders": total_orders,
        "delivered_orders": delivered_orders,
        "total_revenue": total_revenue,
    }


async def get_all_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User))
    return list(result.scalars().all())

