"""Analisis liga kantor: standings dan effective ownership (EO) lokal.

EO lokal = rata-rata multiplier pemain di semua tim liga (0 bench, 1 starter,
2 captain, 3 triple captain). Contoh: EO 1.4 = rata-rata tiap lawan dapat 1.4×
poin pemain itu. Kalau kamu punya pemain dengan EO lebih tinggi dari
multiplier-mu sendiri, kamu justru rugi relatif saat dia cetak poin.

Picks lawan hanya terlihat setelah deadline GW lewat.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .api import FPLClient
from .bootstrap import POSITIONS, elements_by_id, finished_events, gameweeks, teams_by_id


@dataclass
class LeagueEntry:
    entry_id: int
    rank: int
    team_name: str
    manager: str
    event_total: int
    total: int
    active_chip: str | None = None
    captain: int | None = None
    multipliers: dict[int, int] = field(default_factory=dict)  # element -> multiplier


@dataclass
class PlayerEO:
    id: int
    name: str
    team: str
    position: str
    owned_pct: float  # % tim liga yang punya di 15 pemain
    start_pct: float  # % yang memainkan (multiplier > 0)
    captain_pct: float
    eo: float  # effective ownership (rata-rata multiplier)


@dataclass
class LeagueReport:
    league_id: int
    league_name: str
    gw: int
    entries: list[LeagueEntry]
    eo: list[PlayerEO]

    def entry(self, entry_id: int) -> LeagueEntry | None:
        return next((e for e in self.entries if e.entry_id == entry_id), None)

    def eo_by_id(self) -> dict[int, PlayerEO]:
        return {p.id: p for p in self.eo}


def load_league(client: FPLClient, league_id: int, gw: int | None = None) -> LeagueReport:
    boot = client.bootstrap()
    gws = gameweeks(boot)
    gw = gw or gws.current or 1
    is_finished = gw in finished_events(boot)
    elements = elements_by_id(boot)
    teams = teams_by_id(boot)

    info = client.league_info(league_id)
    rows = client.league_standings(league_id)

    entries: list[LeagueEntry] = []
    for r in rows:
        e = LeagueEntry(
            entry_id=r["entry"],
            rank=r["rank"],
            team_name=r["entry_name"],
            manager=r["player_name"],
            event_total=r["event_total"],
            total=r["total"],
        )
        picks = client.entry_picks(e.entry_id, gw, finished=is_finished)
        e.active_chip = picks.get("active_chip")
        for p in picks["picks"]:
            e.multipliers[p["element"]] = p["multiplier"]
            if p["is_captain"]:
                e.captain = p["element"]
        entries.append(e)

    return LeagueReport(
        league_id=league_id,
        league_name=info["name"],
        gw=gw,
        entries=entries,
        eo=compute_eo(entries, elements, teams),
    )


def compute_eo(
    entries: list[LeagueEntry],
    elements: dict[int, dict[str, Any]],
    teams: dict[int, dict[str, Any]],
    exclude_entry: int | None = None,
) -> list[PlayerEO]:
    pool = [e for e in entries if e.entry_id != exclude_entry]
    n = len(pool) or 1
    owned: dict[int, int] = defaultdict(int)
    started: dict[int, int] = defaultdict(int)
    capped: dict[int, int] = defaultdict(int)
    mult_sum: dict[int, int] = defaultdict(int)
    for e in pool:
        for eid, m in e.multipliers.items():
            owned[eid] += 1
            mult_sum[eid] += m
            if m > 0:
                started[eid] += 1
        if e.captain:
            capped[e.captain] += 1

    out = []
    for eid in owned:
        el = elements[eid]
        out.append(
            PlayerEO(
                id=eid,
                name=el["web_name"],
                team=teams[el["team"]]["short_name"],
                position=POSITIONS[el["element_type"]],
                owned_pct=100 * owned[eid] / n,
                start_pct=100 * started[eid] / n,
                captain_pct=100 * capped[eid] / n,
                eo=mult_sum[eid] / n,
            )
        )
    return sorted(out, key=lambda p: p.eo, reverse=True)
