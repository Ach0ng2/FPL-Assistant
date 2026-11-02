import numpy as np
from fpl_assistant.optimizer import solve_transfers
from fpl_assistant.squad import SquadPlayer, TeamState
from fpl_assistant.xp import PlayerXP


def test_optimizer_transfers():
    # Buat dummy squad 15 pemain dengan 10 tim berbeda (maks 2 pemain per tim)
    players = []
    all_xp = {}
    positions = ["GK"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
    for i in range(1, 16):
        pos = positions[i - 1]
        team_id = (i % 8) + 1  # Tim 1 sampai 8
        p = SquadPlayer(
            id=i,
            name=f"Player_{i}",
            team=f"T{team_id}",
            position=pos,
            squad_slot=i,
            is_captain=(i == 1),
            is_vice=(i == 2),
            now_cost=50,
            purchase_price=50,
            selling_price=50,
            status="a",
            chance_next=100,
            news="",
            form=2.0,
            total_points=20,
            ep_next=2.0,
        )
        players.append(p)
        all_xp[i] = PlayerXP(i, p.name, team_id, pos, 50, {10: 2.0, 11: 2.0})

    # Tambahkan pemain target transfer dengan xP tinggi (Tim 9)
    target_id = 99
    all_xp[target_id] = PlayerXP(target_id, "SuperStar", 9, "FWD", 50, {10: 10.0, 11: 10.0})

    boot = {
        "elements": [
            {
                "id": p.id,
                "team": all_xp[p.id].team_id,
                "element_type": 1 if p.position == "GK" else 2 if p.position == "DEF" else 3 if p.position == "MID" else 4,
                "status": "a",
            }
            for p in players
        ]
        + [{"id": 99, "team": 9, "element_type": 4, "status": "a"}]
    }

    state = TeamState(
        team_id=1,
        team_name="Test",
        manager="Me",
        gw=9,
        next_gw=10,
        bank=10,
        free_transfers=1,
        squad_value_selling=750,
        players=players,
        chips_used=[],
        chips_available=[],
        overall_points=100,
        overall_rank=1,
    )

    plan = solve_transfers(state, all_xp, boot, [10, 11], max_transfers_to_consider=1)
    assert len(plan.transfers_in) == 1
    assert plan.transfers_in[0].element_id == target_id
    assert plan.hits_taken == 0
