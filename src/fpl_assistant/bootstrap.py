"""Helper untuk bootstrap-static: gameweek, tim, posisi, chip."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


@dataclass(frozen=True)
class Gameweeks:
    current: int | None  # GW yang deadline-nya sudah lewat paling akhir
    next: int | None  # GW yang akan datang (target rekomendasi)
    current_finished: bool
    next_deadline: datetime | None


def gameweeks(bootstrap: dict[str, Any]) -> Gameweeks:
    current = next_ = None
    finished = False
    deadline = None
    for ev in bootstrap["events"]:
        if ev.get("is_current"):
            current = ev["id"]
            finished = bool(ev.get("finished"))
        if ev.get("is_next"):
            next_ = ev["id"]
            deadline = datetime.fromisoformat(ev["deadline_time"].replace("Z", "+00:00"))
    return Gameweeks(current, next_, finished, deadline)


def finished_events(bootstrap: dict[str, Any]) -> set[int]:
    return {ev["id"] for ev in bootstrap["events"] if ev.get("finished")}


def teams_by_id(bootstrap: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {t["id"]: t for t in bootstrap["teams"]}


def elements_by_id(bootstrap: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {e["id"]: e for e in bootstrap["elements"]}


def chip_windows(bootstrap: dict[str, Any]) -> list[dict[str, Any]]:
    """List chip yang tersedia musim ini: name, start_event, stop_event."""
    return [
        {"name": c["name"], "start_event": c["start_event"], "stop_event": c["stop_event"]}
        for c in bootstrap["chips"]
    ]


def max_free_transfers(bootstrap: dict[str, Any]) -> int:
    extra = bootstrap.get("game_settings", {}).get("max_extra_free_transfers", 4)
    return 1 + int(extra)
