"""Pemilihan Captain, Vice-Captain, dan Starting 11 berbasis xP & EO Liga Kantor.

Strategi:
- Shield (Aman): Pemain dengan xP tinggi + EO liga tinggi (melindungi posisi).
- Differential (Kejar): Pemain dengan xP tinggi tapi EO liga rendah / 0 (potensi naik drastis bila meledak).
- Starting 11: 1 GK, min 3 DEF, min 2 MID, min 1 FWD (total 11) memaksimalkan xP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .league import PlayerEO
from .xp import PlayerXP


@dataclass
class CaptainAdvice:
    captain: PlayerXP
    vice_captain: PlayerXP
    captain_mode: str  # "SHIELD (Aman)" atau "DIFFERENTIAL (Kejar)"
    captain_eo: float
    reason: str


@dataclass
class LineupAdvice:
    starting_11: list[PlayerXP]
    bench: list[PlayerXP]
    captain_advice: CaptainAdvice
    projected_points: float


def select_best_lineup(
    squad: list[PlayerXP],
    target_gw: int,
    league_eo: list[PlayerEO],
    chasing: bool = True,
) -> LineupAdvice:
    """Memilih 11 starter, 4 bench, serta C dan VC untuk target_gw."""
    eo_map = {p.id: p for p in league_eo}

    # Urutkan pemain berdasarkan xP target_gw menurun
    squad_sorted = sorted(squad, key=lambda p: p.xp_by_gw.get(target_gw, 0.0), reverse=True)

    gks = [p for p in squad_sorted if p.position == "GK"]
    defs = [p for p in squad_sorted if p.position == "DEF"]
    mids = [p for p in squad_sorted if p.position == "MID"]
    fwds = [p for p in squad_sorted if p.position == "FWD"]

    # Wajib: 1 GK, 3 DEF, 2 MID, 1 FWD (total 7)
    starters: list[PlayerXP] = [gks[0]] + defs[:3] + mids[:2] + fwds[:1]
    remaining = defs[3:] + mids[2:] + fwds[1:]

    # Ambil 4 pemain outfield dengan xP tertinggi dari sisa pemain
    remaining_sorted = sorted(remaining, key=lambda p: p.xp_by_gw.get(target_gw, 0.0), reverse=True)
    starters.extend(remaining_sorted[:4])

    starter_ids = {p.element_id for p in starters}
    bench = [p for p in squad if p.element_id not in starter_ids]

    # Bench order: GK cadangan di slot 1 bench, sisanya berdasarkan xP
    bench_gk = [p for p in bench if p.position == "GK"]
    bench_outfield = sorted(
        [p for p in bench if p.position != "GK"],
        key=lambda p: p.xp_by_gw.get(target_gw, 0.0),
        reverse=True,
    )
    ordered_bench = bench_gk + bench_outfield

    # Rekomendasi Captain:
    # Jika chasing (tertinggal di liga) dan ada differential kuat (xP bagus, EO rendah), sarankan differential
    # Jika tidak atau shield mode: ambil xP tertinggi / EO tertinggi
    candidates = sorted(starters, key=lambda p: p.xp_by_gw.get(target_gw, 0.0), reverse=True)
    top_xp = candidates[0]
    second_xp = candidates[1] if len(candidates) > 1 else candidates[0]

    top_eo = eo_map.get(top_xp.element_id)
    eo_val = top_eo.eo if top_eo else 0.0

    if chasing and eo_val < 0.5:
        mode = "DIFFERENTIAL (Kejar Point)"
        reason = f"{top_xp.web_name} punya xP tertinggi ({top_xp.xp_by_gw.get(target_gw, 0):.1f}) dan EO lawan rendah ({eo_val:.2f}) -> Peluang emas memangkas gap!"
    else:
        mode = "SHIELD (Aman)"
        reason = f"{top_xp.web_name} punya proyeksi xP terbaik ({top_xp.xp_by_gw.get(target_gw, 0):.1f})."

    captain_advice = CaptainAdvice(
        captain=top_xp,
        vice_captain=second_xp,
        captain_mode=mode,
        captain_eo=eo_val,
        reason=reason,
    )

    # Total proyeksi poin (11 starter + captain double poin)
    proj_pts = sum(p.xp_by_gw.get(target_gw, 0.0) for p in starters) + top_xp.xp_by_gw.get(target_gw, 0.0)

    return LineupAdvice(
        starting_11=starters,
        bench=ordered_bench,
        captain_advice=captain_advice,
        projected_points=round(proj_pts, 1),
    )
