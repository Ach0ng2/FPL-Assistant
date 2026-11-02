"""Penyimpanan override skuad lokal untuk transfer yang dilakukan sebelum deadline.

FPL Public API sengaja menyembunyikan transfer gameweek aktif sampai deadline
berakhir agar strategi manajer tidak bisa diintip lawan. Modul ini memungkinkan
user mencatat transfer baru agar kalkulasi dan tampilan bot langsung update.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT

OVERRIDE_FILE = PROJECT_ROOT / "data" / "pending_transfers.json"


def load_pending_transfers() -> dict[str, Any]:
    if not OVERRIDE_FILE.exists():
        return {"gw": None, "transfers": []}
    try:
        return json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"gw": None, "transfers": []}


def save_pending_transfer(gw: int, out_id: int, in_id: int) -> None:
    data = load_pending_transfers()
    if data.get("gw") != gw:
        data = {"gw": gw, "transfers": []}
    # Hapus jika out_id sudah pernah dicatat
    data["transfers"] = [t for t in data["transfers"] if t["out_id"] != out_id]
    data["transfers"].append({"out_id": out_id, "in_id": in_id})
    OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def clear_pending_transfers() -> None:
    if OVERRIDE_FILE.exists():
        OVERRIDE_FILE.unlink(missing_ok=True)
