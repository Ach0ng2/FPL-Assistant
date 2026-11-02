"""State tim user: squad, bank, harga jual, free transfer, chip tersisa.

Endpoint `/my-team/` (butuh login) memberi angka pasti, tapi kita sengaja
hanya pakai endpoint publik. Karena itu:
- Harga jual diestimasi dari riwayat transfer (aturan FPL: profit dibagi 2,
  dibulatkan ke bawah per 0.1m).
- Free transfer diestimasi dari riwayat per GW.
- Transfer yang sudah dibuat untuk GW berikutnya tapi belum lewat deadline
  tidak terlihat di API publik.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .api import FPLClient
from .bootstrap import (
    POSITIONS,
    chip_windows,
    elements_by_id,
    finished_events,
    gameweeks,
    max_free_transfers,
    teams_by_id,
)


@dataclass
class SquadPlayer:
    id: int
    name: str
    team: str
    position: str
    squad_slot: int  # 1-11 starter, 12-15 bench
    is_captain: bool
    is_vice: bool
    now_cost: int  # dalam 0.1m
    purchase_price: int
    selling_price: int
    status: str  # a=available, d=doubt, i=injured, s=suspended, u=unavailable
    chance_next: int | None
    news: str
    form: float
    total_points: int
    ep_next: float


@dataclass
class TeamState:
    team_id: int
    team_name: str
    manager: str
    gw: int  # GW asal picks
    next_gw: int | None
    bank: int
    free_transfers: int
    squad_value_selling: int
    players: list[SquadPlayer]
    chips_used: list[dict[str, Any]]
    chips_available: list[dict[str, Any]]
    overall_points: int
    overall_rank: int | None
    warnings: list[str] = field(default_factory=list)

    @property
    def budget(self) -> int:
        """Total dana bila semua pemain dijual (bank + harga jual)."""
        return self.bank + self.squad_value_selling


def selling_price(purchase: int, now: int) -> int:
    if now <= purchase:
        return now
    return purchase + (now - purchase) // 2


def estimate_free_transfers(history: dict[str, Any], up_to_gw: int, max_ft: int) -> int:
    """FT yang tersedia untuk GW `up_to_gw + 1`.

    GW1 = transfer tak terbatas, mulai GW2 dapat 1 FT. Setiap GW:
    next = min(max_ft, max(ft - transfers, 0) + 1). Saat WC/FH dimainkan,
    FT yang tersimpan tidak terpakai (aturan sejak 24/25).
    """
    chip_by_event = {c["event"]: c["name"] for c in history.get("chips", [])}
    rows = {r["event"]: r for r in history.get("current", [])}
    ft = 1
    for gw in range(2, up_to_gw + 1):
        row = rows.get(gw)
        transfers = row["event_transfers"] if row else 0
        if chip_by_event.get(gw) in {"wildcard", "freehit"}:
            transfers = 0
        ft = min(max_ft, max(ft - transfers, 0) + 1)
    return ft


def _purchase_prices(
    transfers: list[dict[str, Any]],
    elements: dict[int, dict[str, Any]],
    freehit_events: set[int],
) -> dict[int, int]:
    """Harga beli terakhir tiap pemain (transfer FH diabaikan karena squad di-revert)."""
    prices: dict[int, int] = {}
    for t in sorted(transfers, key=lambda t: t["time"]):
        if t["event"] in freehit_events:
            continue
        prices[t["element_in"]] = t["element_in_cost"]
    # Pemain dari squad awal: harga awal musim.
    for eid, el in elements.items():
        prices.setdefault(eid, el["now_cost"] - el.get("cost_change_start", 0))
    return prices


def load_team_state(client: FPLClient, team_id: int) -> TeamState:
    boot = client.bootstrap()
    gws = gameweeks(boot)
    finished = finished_events(boot)
    elements = elements_by_id(boot)
    teams = teams_by_id(boot)

    entry = client.entry(team_id)
    history = client.entry_history(team_id)
    transfers = client.entry_transfers(team_id)

    gw = gws.current or 1
    picks = client.entry_picks(team_id, gw, finished=gw in finished)
    warnings: list[str] = []

    # Kalau GW sekarang pakai Free Hit, squad "asli" adalah squad GW sebelumnya.
    if picks.get("active_chip") == "freehit" and gw > 1:
        picks = client.entry_picks(team_id, gw - 1, finished=True)
        warnings.append(f"GW{gw} pakai Free Hit; squad diambil dari GW{gw - 1}.")

    freehit_events = {c["event"] for c in history.get("chips", []) if c["name"] == "freehit"}
    purchase = _purchase_prices(transfers, elements, freehit_events)

    players: list[SquadPlayer] = []
    for p in picks["picks"]:
        el = elements[p["element"]]
        buy = purchase[el["id"]]
        players.append(
            SquadPlayer(
                id=el["id"],
                name=el["web_name"],
                team=teams[el["team"]]["short_name"],
                position=POSITIONS[el["element_type"]],
                squad_slot=p["position"],
                is_captain=p["is_captain"],
                is_vice=p["is_vice_captain"],
                now_cost=el["now_cost"],
                purchase_price=buy,
                selling_price=selling_price(buy, el["now_cost"]),
                status=el["status"],
                chance_next=el.get("chance_of_playing_next_round"),
                news=el.get("news") or "",
                form=float(el.get("form") or 0),
                total_points=el["total_points"],
                ep_next=float(el.get("ep_next") or 0),
            )
        )

    bank = picks["entry_history"]["bank"]
    max_ft = max_free_transfers(boot)
    ft = estimate_free_transfers(history, gw, max_ft)

    chips_used = [{"name": c["name"], "event": c["event"]} for c in history.get("chips", [])]
    chips_available = _available_chips(chip_windows(boot), chips_used, gws.next or gw)

    return TeamState(
        team_id=team_id,
        team_name=entry["name"],
        manager=f'{entry["player_first_name"]} {entry["player_last_name"]}',
        gw=gw,
        next_gw=gws.next,
        bank=bank,
        free_transfers=ft,
        squad_value_selling=sum(p.selling_price for p in players),
        players=sorted(players, key=lambda p: p.squad_slot),
        chips_used=chips_used,
        chips_available=chips_available,
        overall_points=entry.get("summary_overall_points") or 0,
        overall_rank=entry.get("summary_overall_rank"),
        warnings=warnings,
    )


def _available_chips(
    windows: list[dict[str, Any]], used: list[dict[str, Any]], from_gw: int
) -> list[dict[str, Any]]:
    """Chip yang belum dipakai di window-nya dan window-nya belum lewat."""
    available = []
    for w in windows:
        used_here = any(
            u["name"] == w["name"] and w["start_event"] <= u["event"] <= w["stop_event"]
            for u in used
        )
        if not used_here and w["stop_event"] >= from_gw:
            available.append(w)
    return sorted(available, key=lambda w: (w["stop_event"], w["name"]))
