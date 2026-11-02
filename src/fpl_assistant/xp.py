"""Model Expected Points (xP) untuk gameweek mendatang.

xP dihitung berbasis:
- Form baseline pemain (poin rata-rata per game / form recent)
- Status ketersediaan & chance of playing
- Fixture difficulty (FDR home/away)
- Bobot xG/xA & peran reguler bermain (minutes ratio)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PlayerXP:
    element_id: int
    web_name: str
    team_id: int
    position: str  # GK, DEF, MID, FWD
    now_cost: int  # 0.1m
    xp_by_gw: dict[int, float]  # gw -> xP

    def total_xp(self, gws: list[int]) -> float:
        return sum(self.xp_by_gw.get(gw, 0.0) for gw in gws)


def compute_all_xp(
    bootstrap: dict[str, Any],
    fixtures: list[dict[str, Any]],
    target_gws: list[int],
) -> dict[int, PlayerXP]:
    team_fixtures: dict[int, dict[int, list[dict[str, Any]]]] = {}
    for f in fixtures:
        gw = f.get("event")
        if not gw or gw not in target_gws:
            continue
        th = f["team_h"]
        ta = f["team_a"]
        diff_h = f.get("team_h_difficulty", 3)
        diff_a = f.get("team_a_difficulty", 3)

        team_fixtures.setdefault(th, {}).setdefault(gw, []).append({"diff": diff_h, "is_home": True})
        team_fixtures.setdefault(ta, {}).setdefault(gw, []).append({"diff": diff_a, "is_home": False})

    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    results: dict[int, PlayerXP] = {}

    for el in bootstrap["elements"]:
        eid = el["id"]
        team_id = el["team"]
        pos = pos_map[el["element_type"]]
        cost = el["now_cost"]

        form = float(el.get("form") or 0.0)
        ppg = float(el.get("points_per_game") or 0.0)
        minutes = int(el.get("minutes") or 0)
        status = el.get("status", "a")

        # Chance of playing / cedera
        chance_next = el.get("chance_of_playing_next_round")
        if status in ("u", "i", "s"):
            play_prob = 0.0 if chance_next is None else float(chance_next) / 100.0
        elif status == "d":
            play_prob = 0.5 if chance_next is None else float(chance_next) / 100.0
        else:
            play_prob = 1.0 if chance_next is None else float(chance_next) / 100.0

        # Minutes reliability factor: pemain dengan menit sangat sedikit tidak boleh di-overestimate
        # GW9 sudah lewat -> rata-rata starter reguler sudah main > 450 menit
        if minutes < 90:
            minute_factor = 0.2
        elif minutes < 270:
            minute_factor = 0.6
        else:
            minute_factor = min(1.0, minutes / (9 * 90))

        # Baseline point expectation
        base_xp = ((0.6 * form) + (0.4 * ppg)) * minute_factor

        # xGI contribution (hanya diperhitungkan jika menit bermain cukup untuk menghindari sampel ekstrem)
        if minutes >= 270 and pos in ("MID", "FWD"):
            try:
                xgi_p90 = min(1.5, float(el.get("expected_goal_involvements_per_90") or 0.0))
                base_xp += xgi_p90 * 1.0
            except (ValueError, TypeError):
                pass

        xp_by_gw: dict[int, float] = {}
        for gw in target_gws:
            fxs = team_fixtures.get(team_id, {}).get(gw, [])
            if not fxs:
                xp_by_gw[gw] = 0.0
                continue

            gw_xp = 0.0
            for fx in fxs:
                diff = fx["diff"]  # 1-5
                diff_mult = 1.0 + (3 - diff) * 0.1
                home_boost = 1.08 if fx["is_home"] else 0.94
                gw_xp += base_xp * diff_mult * home_boost

            gw_xp = max(0.0, gw_xp * play_prob)
            xp_by_gw[gw] = round(gw_xp, 2)

        results[eid] = PlayerXP(
            element_id=eid,
            web_name=el["web_name"],
            team_id=team_id,
            position=pos,
            now_cost=cost,
            xp_by_gw=xp_by_gw,
        )

    return results
