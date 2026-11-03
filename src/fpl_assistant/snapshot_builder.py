"""Perluasan cmd_snapshot untuk menyertakan data lengkap rekomendasi, lineup, dan wildcard."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone

from .api import FPLClient
from .bootstrap import elements_by_id, gameweeks, teams_by_id
from .captain import select_best_lineup
from .chips import evaluate_chip_strategy
from .config import Settings
from .league import compute_eo, load_league
from .optimizer import solve_transfers
from .squad import load_team_state
from .wildcard import solve_wildcard_squad
from .xp import compute_all_xp


def generate_full_snapshot(settings: Settings) -> dict:
    with FPLClient(cache_dir=settings.cache_dir, ttl_seconds=settings.cache_ttl_seconds) as client:
        boot = client.bootstrap()
        fixtures = client.fixtures()
        gws = gameweeks(boot)
        target_gw = gws.next or 10
        horizon_gws = list(range(target_gw, target_gw + 3))
        wc_horizon = list(range(target_gw, target_gw + 5))

        state = load_team_state(client, settings.team_id)
        report = load_league(client, settings.league_id)
        elements = elements_by_id(boot)
        teams = teams_by_id(boot)

    all_xp = compute_all_xp(boot, fixtures, wc_horizon)

    # 1. Transfer Plan
    plan = solve_transfers(state, all_xp, boot, horizon_gws, max_transfers_to_consider=2)

    # 2. Lineup Starting 11 Skuad Saat Ini
    current_squad_xp = [all_xp[p.id] for p in state.players if p.id in all_xp]
    lineup = select_best_lineup(current_squad_xp, target_gw, report.eo, chasing=True)

    # 3. Chip Strategy
    chips_plan = evaluate_chip_strategy(state, all_xp, target_gw, wc_horizon)

    # 4. Wildcard Best Squad
    wc_plan = solve_wildcard_squad(state, all_xp, boot, wc_horizon)

    # 5. Rivals EO
    rivals_eo = compute_eo(report.entries, elements, teams, exclude_entry=settings.team_id)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_gw": target_gw,
        "next_deadline": gws.next_deadline.isoformat() if gws.next_deadline else None,
        "team": asdict(state),
        "league": {
            "id": report.league_id,
            "name": report.league_name,
            "gw": report.gw,
            "standings": [
                {k: v for k, v in asdict(e).items() if k != "multipliers"} for e in report.entries
            ],
            "top_rivals_eo": [asdict(p) for p in rivals_eo[:10]],
        },
        "lineup": {
            "projected_points": lineup.projected_points,
            "starting_11": [
                {
                    "id": p.element_id,
                    "name": p.web_name,
                    "team": teams[p.team_id]["short_name"],
                    "position": p.position,
                    "cost": p.now_cost,
                    "xp": p.xp_by_gw.get(target_gw, 0.0),
                    "is_captain": (p.element_id == lineup.captain_advice.captain.element_id),
                    "is_vice": (p.element_id == lineup.captain_advice.vice_captain.element_id),
                }
                for p in lineup.starting_11
            ],
            "bench": [
                {
                    "id": p.element_id,
                    "name": p.web_name,
                    "team": teams[p.team_id]["short_name"],
                    "position": p.position,
                    "cost": p.now_cost,
                    "xp": p.xp_by_gw.get(target_gw, 0.0),
                }
                for p in lineup.bench
            ],
            "captain": {
                "name": lineup.captain_advice.captain.web_name,
                "vice": lineup.captain_advice.vice_captain.web_name,
                "mode": lineup.captain_advice.captain_mode,
                "reason": lineup.captain_advice.reason,
            },
        },
        "recommendation": {
            "transfers_in": [
                {"name": p.web_name, "cost": p.now_cost, "xp_next": p.xp_by_gw.get(target_gw, 0.0)}
                for p in plan.transfers_in
            ],
            "transfers_out": plan.transfers_out,
            "remaining_bank": plan.remaining_bank,
            "hits_taken": plan.hits_taken,
            "net_cost_pts": plan.net_cost_pts,
            "gain_xp": plan.expected_gain_xp,
        },
        "chips": [asdict(c) for c in chips_plan],
        "wildcard_simulation": {
            "total_cost": wc_plan.total_cost,
            "remaining_bank": wc_plan.remaining_bank,
            "total_xp_5gw": wc_plan.total_xp_horizon,
            "squad": [
                {
                    "name": p.web_name,
                    "team": teams[p.team_id]["short_name"],
                    "position": p.position,
                    "cost": p.now_cost,
                    "total_xp": p.total_xp(wc_horizon),
                }
                for p in wc_plan.squad
            ],
        },
    }
