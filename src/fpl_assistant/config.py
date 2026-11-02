"""Konfigurasi runtime. Semua bisa di-override lewat environment variable."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    team_id: int = field(default_factory=lambda: int(os.getenv("FPL_TEAM_ID", "5938868")))
    league_id: int = field(default_factory=lambda: int(os.getenv("FPL_LEAGUE_ID", "1190246")))
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("FPL_DATA_DIR", PROJECT_ROOT / "data"))
    )
    # TTL cache untuk data yang masih bisa berubah (bootstrap, fixtures, standings).
    cache_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("FPL_CACHE_TTL", "1800"))
    )
    telegram_token: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID"))

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "raw"


def get_settings() -> Settings:
    return Settings()
