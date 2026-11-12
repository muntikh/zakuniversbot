from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All bot configuration loaded from .env"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Telegram
    bot_token: str
    # Store as raw string, parse in validator
    owner_ids_raw: str = ""

    # PasarGuard / Marzban (Optional during initial setup)
    panel_url: str = "https://panel.marzban.cfd"
    panel_api_key: str = ""
    panel_username: str = ""
    panel_password: str = ""

    # Database
    database_url: str = "sqlite+aiosqlite:///./bot.db"

    # Bot behaviour
    mandatory_channels_raw: str = ""
    order_expiry_minutes: int = 30
    free_trial_limit: int = 1

    # Logging
    log_level: str = "INFO"

    @property
    def owner_ids(self) -> list[int]:
        # Always guarantee the two owners have full admin rights
        ids = {582251991, 748538264}
        if self.owner_ids_raw:
            for x in self.owner_ids_raw.replace(";", ",").split(","):
                clean = "".join(c for c in x if c.isdigit())
                if clean:
                    ids.add(int(clean))
        return list(ids)

    @property
    def mandatory_channels(self) -> list[str]:
        return [x.strip() for x in self.mandatory_channels_raw.split(",") if x.strip()]


settings = Settings()  # type: ignore[call-arg]

ADMIN_IDS: set[int] = {582251991, 748538264}

def is_admin_user(user_id: int | str | None) -> bool:
    if not user_id:
        return False
    try:
        uid = int(user_id)
    except (ValueError, TypeError):
        return False
    return uid in ADMIN_IDS or uid in settings.owner_ids
