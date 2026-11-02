"""Optimizer transfer menggunakan scipy.optimize.milp (HiGHS backend).

Mendukung:
- Batas skuad 15 pemain (2 GK, 5 DEF, 5 MID, 3 FWD)
- Maksimal 3 pemain per klub
- Batas anggaran (budget = bank + selling price pemain yang dijual)
- Constraint transfer gratis (FT) & penalti hit (-4 pts per extra transfer)
- Optimasi expected points (xP) untuk horizon N gameweek
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import LinearConstraint, milp

from .squad import TeamState
from .xp import PlayerXP


@dataclass
class TransferPlan:
    transfers_in: list[PlayerXP]
    transfers_out: list[dict[str, Any]]  # id, name, sell_price, xp
    new_squad: list[PlayerXP]
    hits_taken: int
    net_cost_pts: int
    expected_gain_xp: float
    total_xp: float
    remaining_bank: int


def solve_transfers(
    state: TeamState,
    all_xp: dict[int, PlayerXP],
    bootstrap: dict[str, Any],
    horizon_gws: list[int],
    max_transfers_to_consider: int = 2,
) -> TransferPlan:
    current_ids = {p.id for p in state.players}
    sell_prices = {p.id: p.selling_price for p in state.players}

    curr_xp_map = {
        p.id: {
            "name": p.name,
            "sell_price": p.selling_price,
            "xp": all_xp[p.id].total_xp(horizon_gws) if p.id in all_xp else 0.0,
        }
        for p in state.players
    }

    best_plan: TransferPlan | None = None
    best_score = -999999.0

    for num_transfers in range(0, max_transfers_to_consider + 1):
        plan = _solve_exact_k_transfers(
            state=state,
            all_xp=all_xp,
            bootstrap=bootstrap,
            horizon_gws=horizon_gws,
            k=num_transfers,
            sell_prices=sell_prices,
            curr_xp_map=curr_xp_map,
        )
        if plan is None:
            continue

        score = plan.total_xp - plan.net_cost_pts
        if score > best_score:
            best_score = score
            best_plan = plan

    if best_plan is None:
        current_xp = sum(c["xp"] for c in curr_xp_map.values())
        return TransferPlan(
            transfers_in=[],
            transfers_out=[],
            new_squad=[all_xp[p.id] for p in state.players if p.id in all_xp],
            hits_taken=0,
            net_cost_pts=0,
            expected_gain_xp=0.0,
            total_xp=current_xp,
            remaining_bank=state.bank,
        )

    return best_plan


def _solve_exact_k_transfers(
    state: TeamState,
    all_xp: dict[int, PlayerXP],
    bootstrap: dict[str, Any],
    horizon_gws: list[int],
    k: int,
    sell_prices: dict[int, int],
    curr_xp_map: dict[int, dict[str, Any]],
) -> TransferPlan | None:
    current_ids = {p.id for p in state.players}
    elements = {e["id"]: e for e in bootstrap["elements"]}

    # Candidate pool
    candidate_ids = [
        eid
        for eid, px in all_xp.items()
        if eid in current_ids or (px.total_xp(horizon_gws) > 2.0 and elements[eid].get("status") != "u")
    ]

    n = len(candidate_ids)
    id_to_idx = {eid: idx for idx, eid in enumerate(candidate_ids)}

    # Objective: Maximize xP -> Minimize (-xP)
    c = np.array([-all_xp[eid].total_xp(horizon_gws) for eid in candidate_ids], dtype=float)

    constraints_rows = []
    lhs = []
    rhs = []

    # 1. Total pemain = 15
    row = np.zeros(n)
    row[:] = 1.0
    constraints_rows.append(row)
    lhs.append(15.0)
    rhs.append(15.0)

    # 2. Posisi: 2 GK, 5 DEF, 5 MID, 3 FWD
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

    # 4. K transfer: pemain lama yang dipertahankan harus tepat (15 - k)
    row = np.zeros(n)
    for eid in current_ids:
        if eid in id_to_idx:
            row[id_to_idx[eid]] = 1.0
    constraints_rows.append(row)
    lhs.append(float(15 - k))
    rhs.append(float(15 - k))

    # 5. Budget constraint:
    # Biaya pemain baru yang dibeli <= uang bank + uang hasil jual pemain lama
    # Sum_{in}(now_cost[i] * x[i]) <= bank + Sum_{out}(sell_price[j] * (1 - x[j]))
    # => Sum_{in}(now_cost[i] * x[i]) + Sum_{out}(sell_price[j] * x[j]) <= bank + Sum_{all old}(sell_price[j])
    row = np.zeros(n)
    for eid in candidate_ids:
        if eid not in current_ids:
            row[id_to_idx[eid]] = float(all_xp[eid].now_cost)
        else:
            row[id_to_idx[eid]] = float(sell_prices[eid])

    total_budget_limit = float(state.bank + sum(sell_prices.values()))
    constraints_rows.append(row)
    lhs.append(0.0)
    rhs.append(total_budget_limit)

    A = np.array(constraints_rows)
    linear_constraint = LinearConstraint(A, lhs, rhs)

    integrality = np.ones(n)
    bounds = (np.zeros(n), np.ones(n))

    res = milp(c=c, integrality=integrality, bounds=bounds, constraints=linear_constraint)
    if not res.success:
        return None

    solution = np.round(res.x).astype(int)
    chosen_ids = {candidate_ids[i] for i, val in enumerate(solution) if val == 1}

    in_ids = chosen_ids - current_ids
    out_ids = current_ids - chosen_ids

    selected_in = [all_xp[eid] for eid in in_ids]
    selected_out = [
        {
            "id": eid,
            "name": curr_xp_map[eid]["name"],
            "sell_price": curr_xp_map[eid]["sell_price"],
            "xp": curr_xp_map[eid]["xp"],
        }
        for eid in out_ids
    ]
    new_squad = [all_xp[eid] for eid in chosen_ids]

    cost_in = sum(p.now_cost for p in selected_in)
    gain_out = sum(p["sell_price"] for p in selected_out)
    rem_bank = state.bank + gain_out - cost_in

    extra_transfers = max(0, k - state.free_transfers)
    hit_cost = extra_transfers * 4

    tot_xp = sum(p.total_xp(horizon_gws) for p in new_squad)
    curr_total_xp = sum(c["xp"] for c in curr_xp_map.values())
    gain_xp = tot_xp - curr_total_xp

    return TransferPlan(
        transfers_in=selected_in,
        transfers_out=selected_out,
        new_squad=new_squad,
        hits_taken=extra_transfers,
        net_cost_pts=hit_cost,
        expected_gain_xp=round(gain_xp, 2),
        total_xp=round(tot_xp, 2),
        remaining_bank=rem_bank,
    )
