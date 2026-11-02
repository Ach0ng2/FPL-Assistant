from fpl_assistant.league import LeagueEntry, compute_eo
from fpl_assistant.squad import _available_chips, estimate_free_transfers, selling_price


def test_selling_price_profit_halved_rounded_down():
    assert selling_price(50, 50) == 50
    assert selling_price(50, 51) == 50  # +0.1 -> profit 0
    assert selling_price(50, 53) == 51  # +0.3 -> profit 0.1
    assert selling_price(50, 48) == 48  # rugi ditanggung penuh


def _hist(transfers_by_gw, chips=()):
    return {
        "current": [{"event": gw, "event_transfers": t} for gw, t in transfers_by_gw.items()],
        "chips": [{"name": n, "event": e} for n, e in chips],
    }


def test_free_transfers_banking_and_cap():
    # Kasus nyata AchongFC s/d GW9 -> 2 FT untuk GW10.
    h = _hist({1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 5, 7: 0, 8: 3, 9: 0})
    assert estimate_free_transfers(h, 9, max_ft=5) == 2
    # Tidak transfer 8 GW -> mentok di 5.
    assert estimate_free_transfers(_hist({}), 9, max_ft=5) == 5


def test_free_transfers_preserved_on_wildcard():
    h = _hist({2: 0, 3: 0, 4: 12}, chips=[("wildcard", 4)])
    assert estimate_free_transfers(h, 4, max_ft=5) == 4


def test_available_chips_respects_windows():
    windows = [
        {"name": "wildcard", "start_event": 2, "stop_event": 19},
        {"name": "wildcard", "start_event": 20, "stop_event": 38},
        {"name": "3xc", "start_event": 1, "stop_event": 19},
    ]
    used = [{"name": "wildcard", "event": 5}]
    names = [(c["name"], c["stop_event"]) for c in _available_chips(windows, used, 10)]
    assert names == [("3xc", 19), ("wildcard", 38)]
    # Lewat GW19 -> chip paruh pertama hangus.
    assert [c["name"] for c in _available_chips(windows, [], 20)] == ["wildcard"]


def test_compute_eo_counts_captain_double():
    elements = {1: {"web_name": "A", "team": 1, "element_type": 4}, 2: {"web_name": "B", "team": 1, "element_type": 3}}
    teams = {1: {"short_name": "XXX"}}
    entries = [
        LeagueEntry(1, 1, "t1", "m1", 0, 0, captain=1, multipliers={1: 2, 2: 1}),
        LeagueEntry(2, 2, "t2", "m2", 0, 0, captain=2, multipliers={1: 1, 2: 0}),
        LeagueEntry(3, 3, "me", "me", 0, 0, captain=2, multipliers={2: 2}),
    ]
    eo = {p.id: p for p in compute_eo(entries, elements, teams, exclude_entry=3)}
    assert eo[1].eo == 1.5 and eo[1].captain_pct == 50
    assert eo[2].eo == 0.5 and eo[2].start_pct == 50 and eo[2].owned_pct == 100
