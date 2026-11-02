"""Solver khusus untuk merancang Best 15 Squad saat Wildcard atau Free Hit aktif."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import LinearConstraint, milp

from .squad import TeamState
from .xp import PlayerXP


@dataclass
class WildcardSquadPlan:
    squad: list[PlayerXP]
    total_cost: int
    remaining_bank: int
    total_xp_horizon: float
    horizon_gws: list[int]


def solve_wildcard_squad(
    state: TeamState,
    all_xp: dict[int, PlayerXP],
    bootstrap: dict[str, Any],
    horizon_gws: list[int],
) -> WildcardSquadPlan:
    """Membangun 15 pemain terbaik dari nol sesuai budget maksimal tim."""
    elements = {e["id"]: e for e in bootstrap["elements"]}
    budget = state.budget

    # Filter kandidat pemain aktif dengan xP rasional
    candidate_ids = [
        eid
        for eid, px in all_xp.items()
        if px.total_xp(horizon_gws) > 3.0 and elements[eid].get("status") != "u"
    ]

    n = len(candidate_ids)
    id_to_idx = {eid: idx for idx, eid in enumerate(candidate_ids)}

    # Objective: Maksimalkan total xP skuad untuk rentang horizon
    c = np.array([-all_xp[eid].total_xp(horizon_gws) for eid in candidate_ids], dtype=float)

    constraints_rows = []
    lhs = []
    rhs = []

    # 1. Tepat 15 pemain
    row = np.ones(n)
    constraints_rows.append(row)
    lhs.append(15.0)
    rhs.append(15.0)

    # 2. Batas Posisi: 2 GK, 5 DEF, 5 MID, 3 FWD
    pos_targets = {"GK": 2.0, "DEF": 5.0, "MID": 5.0, "FWD": 3.0}
    for pos, target in pos_targets.items():
        row = np.zeros(n)
        for eid in candidate_ids:
            if all_xp[eid].position == pos:
                row[id_to_idx[eid]] = 1.0
        constraints_rows.append(row)
        lhs.append(target)
        rhs.append(target)

    # 3. Maksimal 3 pemain per klub
    teams = {e["team"] for e in elements.values()}
    for tid in teams:
        row = np.zeros(n)
        for eid in candidate_ids:
            if all_xp[eid].team_id == tid:
                row[id_to_idx[eid]] = 1.0
        constraints_rows.append(row)
        lhs.append(0.0)
        rhs.append(3.0)

    # 4. Budget Constraint: Total harga pembelian <= budget skuad
    row = np.array([float(all_xp[eid].now_cost) for eid in candidate_ids], dtype=float)
    constraints_rows.append(row)
    lhs.append(0.0)
    rhs.append(float(budget))

    A = np.array(constraints_rows)
    linear_constraint = LinearConstraint(A, lhs, rhs)

    integrality = np.ones(n)
    bounds = (np.zeros(n), np.ones(n))

    res = milp(c=c, integrality=integrality, bounds=bounds, constraints=linear_constraint)
    if not res.success:
        # Fallback jika solver gagal
        return WildcardSquadPlan(
            squad=[all_xp[p.id] for p in state.players if p.id in all_xp],
            total_cost=state.squad_value_selling,
            remaining_bank=state.bank,
            total_xp_horizon=sum(all_xp[p.id].total_xp(horizon_gws) for p in state.players if p.id in all_xp),
            horizon_gws=horizon_gws,
        )

    solution = np.round(res.x).astype(int)
    chosen_squad = [all_xp[candidate_ids[i]] for i, val in enumerate(solution) if val == 1]

    # Urutkan berdasarkan posisi lalu xP
    pos_order = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}
    chosen_squad.sort(key=lambda p: (pos_order[p.position], -p.total_xp(horizon_gws)))

    tot_cost = sum(p.now_cost for p in chosen_squad)
    rem_bank = budget - tot_cost
    tot_xp = sum(p.total_xp(horizon_gws) for p in chosen_squad)

    return WildcardSquadPlan(
        squad=chosen_squad,
        total_cost=tot_cost,
        remaining_bank=rem_bank,
        total_xp_horizon=round(tot_xp, 1),
        horizon_gws=horizon_gws,
    )
