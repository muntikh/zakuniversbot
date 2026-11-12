import asyncio
import sys
from decimal import Decimal

from sqlalchemy import select

from bot.db.database import AsyncSessionLocal, init_db
from bot.db.models import Plan
from bot.services.pasarguard import panel

# Default pricing strategy (per GB or base estimation in Tomans)
# 1-30 days: ~7,000 to ~9,000 T per GB
# 90 days: ~8,000 to ~10,000 T per GB
# Unlimited plans: special fixed price

def estimate_price(data_gb: float, duration_days: int) -> int:
    """Calculates price with updated tariffs: 4,800 T per GB for 1-6 months, 4,000 T per GB for 1-year."""
    if data_gb == 0:  # Unlimited traffic
        if duration_days <= 30:
            return 350000
        elif duration_days <= 90:
            return 850000
        return 1500000

    # 1-year stays untouched at 4,000 T/GB
    if duration_days >= 365:
        return max(20000, int(data_gb * 4000))

    # 1-month 50 GB is strictly 240,000 T
    if data_gb == 50 and duration_days <= 30:
        return 240000

    # Other multi-month plans scaled like month 1 (4,800 T/GB)
    return max(20000, int(data_gb * 4800))


async def sync():
    await init_db()
    templates = []
    try:
        await panel.start()
        templates = await panel.get_templates()
        print(f"Fetched {len(templates)} templates from PasarGuard.")
    except Exception as exc:
        print(f"Panel connection unavailable ({exc}), seeding standard offline plans...")
        templates = [
            {"id": 1, "name": "10GB - 30Day", "data_limit": 10 * 1024**3, "expire_duration": 30 * 86400},
            {"id": 2, "name": "20GB - 30Day", "data_limit": 20 * 1024**3, "expire_duration": 30 * 86400},
            {"id": 3, "name": "30GB - 30Day", "data_limit": 30 * 1024**3, "expire_duration": 30 * 86400},
            {"id": 4, "name": "50GB - 30Day", "data_limit": 50 * 1024**3, "expire_duration": 30 * 86400},
            {"id": 5, "name": "100GB - 30Day", "data_limit": 100 * 1024**3, "expire_duration": 30 * 86400},
            {"id": 6, "name": "30GB - 90Day", "data_limit": 30 * 1024**3, "expire_duration": 90 * 86400},
            {"id": 7, "name": "50GB - 90Day", "data_limit": 50 * 1024**3, "expire_duration": 90 * 86400},
            {"id": 8, "name": "100GB - 90Day", "data_limit": 100 * 1024**3, "expire_duration": 90 * 86400},
            {"id": 9, "name": "50GB - 180Day", "data_limit": 50 * 1024**3, "expire_duration": 180 * 86400},
            {"id": 10, "name": "100GB - 180Day", "data_limit": 100 * 1024**3, "expire_duration": 180 * 86400},
        ]

    async with AsyncSessionLocal() as session:
        added = 0
        updated = 0
        for idx, t in enumerate(templates):
            t_id = t["id"]
            name = t["name"]
            data_bytes = t.get("data_limit", 0) or 0
            expire_sec = t.get("expire_duration", 0) or 0

            data_gb = round(data_bytes / (1024**3), 1) if data_bytes else 0
            duration_days = round(expire_sec / 86400) if expire_sec else 0

            price = estimate_price(data_gb, duration_days)

            # Filter low volumes: remove 1-month 20GB and lowest multi-month options
            if duration_days <= 30 and data_gb <= 20:
                is_visible = False
            elif 30 < duration_days <= 60 and data_gb <= 30:
                is_visible = False
            elif 60 < duration_days <= 90 and data_gb <= 40:
                is_visible = False
            elif 90 < duration_days <= 180 and data_gb <= 80:
                is_visible = False
            else:
                is_visible = (duration_days >= 30)

            # Check if plan already exists for this template
            result = await session.execute(
                select(Plan).where(Plan.pasarguard_template_id == t_id)
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.name = name
                existing.data_gb = data_gb
                existing.duration_days = duration_days
                existing.price_toman = price
                existing.show_in_menu = is_visible
                updated += 1
            else:
                p = Plan(
                    name=name,
                    pasarguard_template_id=t_id,
                    data_gb=data_gb,
                    duration_days=duration_days,
                    price_toman=price,
                    order_index=idx,
                    is_active=True,
                    show_in_menu=is_visible,
                    badge_emoji="💎" if data_gb >= 100 or data_gb == 0 else "🔵",
                )
                session.add(p)
                added += 1

        await session.commit()
        print(f"Sync complete: {added} plans added, {updated} plans updated.")

    await panel.stop()

if __name__ == "__main__":
    asyncio.run(sync())
