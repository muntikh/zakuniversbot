from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class BuyStates(StatesGroup):
    choosing_mode = State()       # انتخاب حالت شبکه (نت ملی / عادی)
    choosing_os = State()         # انتخاب سیستم عامل (اندروید / آیفون / ویندوز)
    choosing_duration = State()   # انتخاب دوره (۱، ۳، ۶، ۱۲ ماهه)
    choosing_tier = State()       # دسته‌بندی کاربر (تک‌کاربر، دوکاربر، نامحدود)
    choosing_plan = State()       # انتخاب پلن حجمی
    entering_config_name = State()# انتخاب نام کانفیگ (Zak-*****)
    choosing_payment = State()    # انتخاب روش پرداخت
    entering_discount = State()   # ورود کد تخفیف
    awaiting_receipt = State()    # در انتظار تصویر فیش
    confirming_wallet = State()   # تایید نهایی پرداخت از کیف پول


class RenewStates(StatesGroup):
    choosing_service = State()    # انتخاب سرویس جهت تمدید
    choosing_duration = State()   # انتخاب دوره تمدید
    choosing_plan = State()       # انتخاب پلن تمدید
    choosing_payment = State()    # انتخاب روش پرداخت
    awaiting_receipt = State()    # ارسال فیش تمدید


class ExtraDataStates(StatesGroup):
    choosing_service = State()    # انتخاب سرویس جهت افزودن حجم
    choosing_amount = State()     # انتخاب گیگابایت
    entering_custom_gb = State()  # ورود حجم دلخواه
    choosing_payment = State()    # انتخاب روش پرداخت
    awaiting_receipt = State()    # ارسال فیش حجم اضافه


class WalletStates(StatesGroup):
    choosing_amount = State()         # انتخاب مبلغ شارژ
    entering_custom_amount = State()  # ورود مبلغ دلخواه
    awaiting_deposit_receipt = State()# در انتظار فیش واریزی شارژ کیف پول


class SupportStates(StatesGroup):
    choosing_subject = State()        # انتخاب یا ورود موضوع تیکت
    waiting_custom_subject = State()  # ورود متن موضوع دلخواه
    writing_message = State()         # ارسال متن یا توضیحات تیکت


class AdminSupportReplyStates(StatesGroup):
    writing_reply = State()


class AdminBroadcastStates(StatesGroup):
    choosing_target = State()     # انتخاب مخاطبان
    writing_message = State()     # نوشتن متن
    confirming = State()          # تایید نهایی


class AdminUserSearchStates(StatesGroup):
    waiting_input = State()       # انتظار برای آیدی یا username


class AdminCardStates(StatesGroup):
    waiting_card_number = State()
    waiting_bank_name = State()
