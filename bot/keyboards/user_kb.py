from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from bot.config import is_admin_user

remove_kb = ReplyKeyboardRemove()


# ─────────────────────────────────────────────────────────────
# Main Menu — ReplyKeyboard (Persistent under chat input)
# ─────────────────────────────────────────────────────────────

def main_menu_kb(is_admin: bool = False, user_id: int | None = None) -> ReplyKeyboardMarkup:
    if user_id is not None:
        is_admin = is_admin or is_admin_user(user_id)

    rows = [
        [
            KeyboardButton(text="🚀 خرید سرویس جدید"),
        ],
        [
            KeyboardButton(text="📱 سرویس های من"),
            KeyboardButton(text="♻️ تمدید سرویس"),
        ],
        [
            KeyboardButton(text="💡 آموزش استفاده"),
            KeyboardButton(text="💰 اعتبار من"),
        ],
        [
            KeyboardButton(text="👨‍💻 تماس با پشتیبانی"),
            KeyboardButton(text="👥 معرفی به دوستان"),
        ],
        [
            KeyboardButton(text="♾️ حجم اضافه"),
            KeyboardButton(text="🔍 پیگیری سفارش"),
        ],
    ]
    if is_admin:
        rows.insert(0, [KeyboardButton(text="👑 پنل مدیریت")])

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="یکی از گزینه‌ها را انتخاب کنید...",
    )


# ─────────────────────────────────────────────────────────────
# Main Menu — InlineKeyboard (Colorful rich buttons inside chat)
# ─────────────────────────────────────────────────────────────

def main_menu_inline_kb(is_admin: bool = False, user_id: int | None = None) -> InlineKeyboardMarkup:
    if user_id is not None:
        is_admin = is_admin or is_admin_user(user_id)

    rows = [
        [
            InlineKeyboardButton(text="🚀 خرید سرویس جدید", callback_data="buy:start"),
        ],
        [
            InlineKeyboardButton(text="📱 سرویس های من", callback_data="services:list"),
            InlineKeyboardButton(text="♻️ تمدید سرویس", callback_data="renew:start"),
        ],
        [
            InlineKeyboardButton(text="💡 آموزش استفاده", callback_data="guide:main"),
            InlineKeyboardButton(text="💰 اعتبار من", callback_data="wallet:back_to_account"),
        ],
        [
            InlineKeyboardButton(text="👨‍💻 تماس با پشتیبانی", callback_data="support:start"),
            InlineKeyboardButton(text="👥 معرفی به دوستان", callback_data="wallet:referral"),
        ],
        [
            InlineKeyboardButton(text="♾️ حجم اضافه", callback_data="extra:start"),
            InlineKeyboardButton(text="🔍 پیگیری سفارش", callback_data="tracking:start"),
        ],
    ]
    if is_admin:
        rows.insert(0, [InlineKeyboardButton(text="👑 پنل مدیریت", callback_data="admin:menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─────────────────────────────────────────────────────────────
# Buy Flow Keyboards
# ─────────────────────────────────────────────────────────────

def single_mode_kb() -> InlineKeyboardMarkup:
    """Shows buttons: 'نت ملی' and 'منوی اصلی 🔙' matching Image 1."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="نت ملی", callback_data="buy:loc:national")],
        [InlineKeyboardButton(text="منوی اصلی 🔙", callback_data="buy:cancel")],
    ])

mode_kb = single_mode_kb


def os_selection_kb() -> InlineKeyboardMarkup:
    """Matches Image 2: OS selection."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="آیفون (Ios)", callback_data="buy:os:ios"),
            InlineKeyboardButton(text="اندروید", callback_data="buy:os:android"),
        ],
        [
            InlineKeyboardButton(text="بازگشت 🔙", callback_data="buy:back_to_loc"),
        ],
    ])


def os_plans_kb(os_name: str) -> InlineKeyboardMarkup:
    """Matches Image 3 (iOS) & Image 4 (Android)."""
    rows = []
    if os_name == "android":
        # Android: 3 plans matching Image 4
        rows.append([InlineKeyboardButton(text="1 ماه | 50 گیگ | 259ت", callback_data="buy:plan:android_50gb_1m")])
        rows.append([InlineKeyboardButton(text="2 ماه | 90 گیگ | 385ت", callback_data="buy:plan:android_90gb_2m")])
        rows.append([InlineKeyboardButton(text="3 ماه | 150 گیگ | 420ت", callback_data="buy:plan:android_150gb_3m")])
    else:
        # iOS: 4 plans matching Image 3
        rows.append([InlineKeyboardButton(text="1 ماه | 50 گیگ | 319ت", callback_data="buy:plan:ios_50gb_1m")])
        rows.append([InlineKeyboardButton(text="2 ماه | 90 گیگ | 435ت", callback_data="buy:plan:ios_90gb_2m")])
        rows.append([InlineKeyboardButton(text="3 ماه | 150 گیگ | 500ت", callback_data="buy:plan:ios_150gb_3m")])
        rows.append([InlineKeyboardButton(text="نامحدود | 6 ماه | 3 کاربر", callback_data="buy:plan:ios_unlimited_6m_3u")])

    rows.append([InlineKeyboardButton(text="بازگشت 🔙", callback_data="buy:back_to_os")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def durations_catalog_kb() -> InlineKeyboardMarkup:
    """Clean, uncluttered duration options without redundant emojis."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="۱ ماهه (۳۰ روز)", callback_data="dur:30"),
            InlineKeyboardButton(text="۲ ماهه (۶۰ روز)", callback_data="dur:60"),
        ],
        [
            InlineKeyboardButton(text="۳ ماهه (۹۰ روز)", callback_data="dur:90"),
            InlineKeyboardButton(text="۶ ماهه (۱۸۰ روز)", callback_data="dur:180"),
        ],
        [
            InlineKeyboardButton(text="۱ ساله (۳۶۵ روز)", callback_data="dur:365"),
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="buy:cancel"),
        ],
    ])


def duration_plans_kb(duration: int, options: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    dur_label = {
        30: "1 ماه",
        60: "2 ماه",
        90: "3 ماه",
        180: "6 ماه",
        365: "1 سال",
    }.get(duration, f"{duration} روز")

    for opt in options:
        gb = opt["gb"]
        price = opt["base_price"]
        btn_text = f"{dur_label} | {gb} گیگ | {price:,} تومان"
        rows.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"plan_sel:{duration}:{gb}:{price}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت به انتخاب دوره", callback_data="buy:back_to_dur")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_count_tier_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 تک‌کاربره (بدون اضافه بها)", callback_data="tier_sel:1:0")],
        [InlineKeyboardButton(text="👥 دوکاربره (+۲۰,۰۰۰ تومان)", callback_data="tier_sel:2:20000")],
        [InlineKeyboardButton(text="👨‍👩‍👧 سه کاربره (+۴۰,۰۰۰ تومان)", callback_data="tier_sel:3:40000")],
        [InlineKeyboardButton(text="👨‍👩‍👦‍👦 کاربر نامحدود (+۶۰,۰۰۰ تومان)", callback_data="tier_sel:99:60000")],
        [InlineKeyboardButton(text="🔙 مرحله قبل", callback_data="buy:back_to_plans")],
    ])


def config_name_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 تولید نام تصادفی", callback_data="cfg_name:random")],
        [
            InlineKeyboardButton(text="🔙 مرحله قبل", callback_data="buy:back_to_plans"),
            InlineKeyboardButton(text="❌ انصراف", callback_data="buy:cancel"),
        ],
    ])


def delivery_choice_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 تحویل مستقیم کانفیگ", callback_data=f"user_delivery:direct:{order_id}")],
        [InlineKeyboardButton(text="💰 ذخیره در کیف پول", callback_data=f"user_delivery:wallet:{order_id}")],
    ])


def payment_kb(wallet_balance: int, final_price: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="💳 کارت به کارت", callback_data="pay:card")],
    ]
    if wallet_balance >= final_price:
        rows.append([InlineKeyboardButton(
            text=f"💰 پرداخت از کیف پول (موجودی: {wallet_balance:,} ت)",
            callback_data="pay:wallet",
        )])
    rows += [
        [InlineKeyboardButton(text="🎁 ثبت کد تخفیف", callback_data="pay:discount")],
        [InlineKeyboardButton(text="❌ انصراف از خرید", callback_data="buy:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def discount_cancel_kb() -> InlineKeyboardMarkup:
    """Returns back to payment pre-invoice without cancelling the order."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به پیش‌فاکتور", callback_data="discount:cancel")]
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ انصراف و بازگشت", callback_data="buy:cancel")]
    ])


def after_delivery_kb(sub_url: str = "") -> InlineKeyboardMarkup:
    rows = []
    if sub_url and sub_url.startswith("http"):
        rows.append([InlineKeyboardButton(text="⚙️ ورود به پنل مدیریت سرویس", url=sub_url)])
    rows.append([
        InlineKeyboardButton(text="💡 آموزش استفاده", callback_data="guide:main"),
        InlineKeyboardButton(text="📱 سرویس های من", callback_data="services:list"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_order_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تایید و فعال‌سازی", callback_data=f"admin_confirm:{order_id}"),
            InlineKeyboardButton(text="❌ رد کردن", callback_data=f"admin_reject:{order_id}"),
        ]
    ])


def pending_order_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 لغو سفارش قبلی و خرید جدید", callback_data=f"cancel_order:{order_id}"),
            InlineKeyboardButton(text="📋 مشاهده سفارش قبلی", callback_data=f"view_order:{order_id}"),
        ]
    ])


def account_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 افزایش موجودی (شارژ)", callback_data="wallet:deposit"),
        ],
        [
            InlineKeyboardButton(text="📜 گردش حساب و تراکنش‌ها", callback_data="wallet:history"),
            InlineKeyboardButton(text="👥 معرفی به دوستان (هدیه ۲,۰۰۰ ت)", callback_data="wallet:referral"),
        ],
        [
            InlineKeyboardButton(text="🔙 بستن", callback_data="wallet:close"),
        ],
    ])


def deposit_amounts_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="۵۰,۰۰۰ تومان", callback_data="deposit_amt:50000"),
            InlineKeyboardButton(text="۱۰۰,۰۰۰ تومان", callback_data="deposit_amt:100000"),
        ],
        [
            InlineKeyboardButton(text="۲۰۰,۰۰۰ تومان", callback_data="deposit_amt:200000"),
            InlineKeyboardButton(text="۵۰۰,۰۰۰ تومان", callback_data="deposit_amt:500000"),
        ],
        [
            InlineKeyboardButton(text="✏️ ورود مبلغ دلخواه", callback_data="deposit_amt:custom"),
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به حساب", callback_data="wallet:back_to_account"),
        ],
    ])


def back_to_account_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔙 بازگشت به حساب کاربری", callback_data="wallet:back_to_account"),
        ]
    ])


def admin_deposit_kb(txn_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تایید و شارژ حساب", callback_data=f"admin_dep_confirm:{txn_id}"),
            InlineKeyboardButton(text="❌ رد درخواست", callback_data=f"admin_dep_reject:{txn_id}"),
        ]
    ])
