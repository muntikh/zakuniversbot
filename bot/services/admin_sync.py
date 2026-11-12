from __future__ import annotations

from typing import List, Optional

from aiogram import Bot, types
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.crud import get_setting, set_setting


async def save_admin_receipt_messages(
    session: AsyncSession,
    key: str,
    messages: List[types.Message],
) -> None:
    """Stores chat_id:message_id pairs for an admin notification."""
    refs = [f"{msg.chat.id}:{msg.message_id}" for msg in messages if msg]
    if refs:
        val = ",".join(refs)
        await set_setting(session, f"admin_sync:{key}", val)


async def update_all_admin_receipt_messages(
    bot: Bot,
    session: AsyncSession,
    key: str,
    status_text: str,
    by_user: types.User,
) -> None:
    """
    Updates the caption and removes inline buttons from all admin chat copies
    of a payment receipt when one admin approves or rejects it.
    """
    admin_name = by_user.full_name or (f"@{by_user.username}" if by_user.username else str(by_user.id))
    refs_str = await get_setting(session, f"admin_sync:{key}", "")
    if not refs_str:
        return

    for item in refs_str.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        try:
            chat_id_str, msg_id_str = item.split(":")
            chat_id = int(chat_id_str)
            msg_id = int(msg_id_str)

            final_text = f"{status_text}\n👤 بررسی‌شده توسط: <b>{admin_name}</b>"

            # Try editing caption first (for photo receipts)
            try:
                cap = final_text[:1020] + "..." if len(final_text) > 1024 else final_text
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=msg_id,
                    caption=cap,
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception:
                # If it's a text message or edit_message_caption fails:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=final_text[:4000],
                    parse_mode="HTML",
                    reply_markup=None,
                )
        except Exception as exc:
            # Message might have already been edited, deleted, or unchanged
            logger.debug(f"Could not update admin message {item} for key {key}: {exc}")
