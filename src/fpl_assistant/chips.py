"""Chip Strategy Advisor.

Menganalisis kapan waktu terbaik menggunakan 4 chip paruh pertama (GW1-19):
- Wildcard (WC): Reset total skuad tanpa penalti
- Free Hit (FH): Skuad darurat 1 pekan
- Bench Boost (BB): Poin 4 pemain cadangan ikut dihitung
- Triple Captain (TC): Poin kapten dikali 3

Aturan musim 26/27:
Chip paruh pertama HANGUS jika tidak dipakai sebelum GW19 selesai!
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .squad import TeamState
from .xp import PlayerXP


@dataclass
class ChipAdvice:
    chip_name: str
    status: str  # "AVAILABLE", "USED", "EXPIRED"
    deadline_gw: int
    recommended_gw: str
    urgency: str  # "LOW", "MEDIUM", "HIGH"
    strategy_note: str


def evaluate_chip_strategy(
    state: TeamState,
    all_xp: dict[int, PlayerXP],
    target_gw: int,
    horizon_gws: list[int],
) -> list[ChipAdvice]:
    results: list[ChipAdvice] = []

    # Cek chip paruh pertama yang masih tersedia
    avail_h1 = {c["name"] for c in state.chips_available if c["stop_event"] <= 19}

    # 1. WILDCARD (WC)
    if "wildcard" in avail_h1:
        # Cek kondisi skuad sekarang: berapa pemain cedera/form buruk
        bad_players = [p for p in state.players if p.status != "a" or p.form < 2.5]
        if len(bad_players) >= 4:
            wc_urgency = "HIGH"
            wc_note = f"Ada {len(bad_players)} pemain di skuad bermasalah/form rendah. Pertimbangkan Wildcard segera!"
            wc_rec = f"GW{target_gw} atau GW{target_gw + 1}"
        else:
            wc_urgency = "MEDIUM"
            wc_note = "Skuad inti masih solid. Simpan WC untuk periode jadwal padat (GW14-16) atau sebelum hangus di GW19."
            wc_rec = "GW14 – GW17"

        results.append(
            ChipAdvice(
                chip_name="Wildcard (WC)",
                status="AVAILABLE",
                deadline_gw=19,
                recommended_gw=wc_rec,
                urgency=wc_urgency,
                strategy_note=wc_note,
            )
        )

    # 2. TRIPLE CAPTAIN (TC)
    if "3xc" in avail_h1:
        # Cari pemain dengan lonjakan xP tertinggi di horizon
        top_picks = sorted(all_xp.values(), key=lambda p: p.xp_by_gw.get(target_gw, 0), reverse=True)
        best_p = top_picks[0] if top_picks else None
        best_xp = best_p.xp_by_gw.get(target_gw, 0) if best_p else 0

        if best_xp >= 9.5:
            tc_urgency = "HIGH"
            tc_rec = f"GW{target_gw} ({best_p.web_name})"
            tc_note = f"Ada kandidat kapten dengan proyeksi xP masif ({best_p.web_name}: {best_xp:.1f} pts). Waktu bagus untuk TC!"
        else:
            tc_urgency = "MEDIUM"
            tc_rec = "GW12 – GW16"
            tc_note = "Tunggu laga kandang super mudah tim unggulan (MCI/ARS/LIV) atau pemain bintang lawan tim promosi."

        results.append(
            ChipAdvice(
                chip_name="Triple Captain (TC)",
                status="AVAILABLE",
                deadline_gw=19,
                recommended_gw=tc_rec,
                urgency=tc_urgency,
                strategy_note=tc_note,
            )
        )

    # 3. BENCH BOOST (BB)
    if "bboost" in avail_h1:
        # Evaluasi xP 4 pemain bench skuad saat ini
        bench_players = state.players[11:]
        bench_xp = sum(all_xp[p.id].xp_by_gw.get(target_gw, 0) for p in bench_players if p.id in all_xp)

        if bench_xp >= 16.0:
            bb_urgency = "HIGH"
            bb_rec = f"GW{target_gw}"
            bb_note = f"Bench kamu sangat kuat di GW ini (potensi ~{bench_xp:.1f} pts). Bagus untuk Bench Boost!"
        else:
            bb_urgency = "LOW"
            bb_rec = "Pasca Wildcard (GW15-18)"
            bb_note = "Aktifkan 1 pekan setelah Wildcard ketika ke-15 pemain tim kamu semuanya starter reguler."

        results.append(
            ChipAdvice(
                chip_name="Bench Boost (BB)",
                status="AVAILABLE",
                deadline_gw=19,
                recommended_gw=bb_rec,
                urgency=bb_urgency,
                strategy_note=bb_note,
            )
        )

    # 4. FREE HIT (FH)
    if "freehit" in avail_h1:
        results.append(
            ChipAdvice(
                chip_name="Free Hit (FH)",
                status="AVAILABLE",
                deadline_gw=19,
                recommended_gw="GW18 atau GW19 (Boxing Day / Rotasi Ekstrem)",
                urgency="LOW",
                strategy_note="Simpan untuk Boxing Day / Festive Period (GW18-19) saat banyak pemain inti diistirahatkan mendadak.",
            )
        )

    return results
