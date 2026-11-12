from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────

class AdminLevel(int, enum.Enum):
    USER = 0
    SUPPORT = 1
    ADMIN = 2
    OWNER = 3


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"                   # تازه ایجاد شده
    AWAITING_RECEIPT = "AWAITING_RECEIPT" # در انتظار فیش کاربر
    RECEIPT_SENT = "RECEIPT_SENT"         # فیش ارسال شده — در انتظار ادمین
    CONFIRMED = "CONFIRMED"               # تایید شده — در حال پروویژن
    PROVISIONING = "PROVISIONING"         # در حال ایجاد در پنل
    DELIVERED = "DELIVERED"               # تحویل داده شده
    REJECTED = "REJECTED"                 # رد شده توسط ادمین
    EXPIRED = "EXPIRED"                   # منقضی شده (عدم پرداخت)
    PAID_PENDING_PROVISION = "PAID_PENDING_PROVISION"  # پرداخت شد / پنل محدود است


class PaymentMethod(str, enum.Enum):
    CARD = "CARD"       # کارت به کارت
    WALLET = "WALLET"   # کیف پول داخلی


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    LIMITED = "limited"
    DISABLED = "disabled"


# ─────────────────────────────────────────────────────────────
# Tables
# ─────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128))
    balance_toman: Mapped[int] = mapped_column(Integer, default=0)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_exempt_join: Mapped[bool] = mapped_column(Boolean, default=False)
    admin_level: Mapped[int] = mapped_column(Integer, default=0)
    referral_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, unique=True)
    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    free_trial_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    orders: Mapped[list["Order"]] = relationship(back_populates="user")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    pasarguard_template_id: Mapped[int] = mapped_column(Integer)
    data_gb: Mapped[float] = mapped_column(Float)         # 0 = unlimited
    duration_days: Mapped[int] = mapped_column(Integer)   # 0 = unlimited
    price_toman: Mapped[int] = mapped_column(Integer)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    show_in_menu: Mapped[bool] = mapped_column(Boolean, default=True)
    badge_emoji: Mapped[str] = mapped_column(String(8), default="🔵")

    orders: Mapped[list["Order"]] = relationship(back_populates="plan")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)   # e.g. ORD-00142
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("plans.id"))
    amount_toman: Mapped[int] = mapped_column(Integer)
    discount_applied: Mapped[int] = mapped_column(Integer, default=0)  # percent
    status: Mapped[str] = mapped_column(
        Enum(OrderStatus, name="order_status"), default=OrderStatus.PENDING
    )
    payment_method: Mapped[Optional[str]] = mapped_column(
        Enum(PaymentMethod, name="payment_method"), nullable=True
    )
    receipt_file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    confirmed_by_admin_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    custom_config_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="orders")
    plan: Mapped["Plan"] = relationship(back_populates="orders")
    subscription: Mapped[Optional["Subscription"]] = relationship(back_populates="order")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    order_id: Mapped[str] = mapped_column(String(16), ForeignKey("orders.id"))
    marzban_username: Mapped[str] = mapped_column(String(64), unique=True)
    subscription_url: Mapped[str] = mapped_column(Text)
    expire_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    data_limit_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    used_traffic_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    order: Mapped["Order"] = relationship(back_populates="subscription")


class Discount(Base):
    __tablename__ = "discounts"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    percent: Mapped[int] = mapped_column(Integer)
    max_usage: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TransactionType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"           # شارژ کیف پول (واریز)
    PURCHASE = "PURCHASE"         # خرید سرویس (کسر)
    REFUND = "REFUND"             # برگشت وجه
    ADMIN_ADJUST = "ADMIN_ADJUST" # تنظیم دستی ادمین


class TransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    REJECTED = "REJECTED"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # e.g. TXN-10492
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"))
    amount_toman: Mapped[int] = mapped_column(Integer)             # مثبت برای افزایش، منفی برای کسر
    balance_after: Mapped[int] = mapped_column(Integer, default=0) # موجودی پس از تراکنش
    transaction_type: Mapped[str] = mapped_column(
        Enum(TransactionType, name="transaction_type"), default=TransactionType.DEPOSIT
    )
    status: Mapped[str] = mapped_column(
        Enum(TransactionStatus, name="transaction_status"), default=TransactionStatus.PENDING
    )
    description: Mapped[str] = mapped_column(String(256), default="")
    receipt_file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    verified_by_admin_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="transactions")


class BotSetting(Base):
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
