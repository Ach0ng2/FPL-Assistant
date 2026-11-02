"""CLI: `uv run fpl-assistant <perintah>`."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from rich.console import Console
from rich.table import Table

from .api import FPLClient
from .bootstrap import gameweeks
from .config import Settings, get_settings
from .league import compute_eo, load_league
from .squad import TeamState, load_team_state
from .bootstrap import elements_by_id, teams_by_id

WIB = timezone(timedelta(hours=7))
CHIP_LABEL = {"wildcard": "Wildcard", "freehit": "Free Hit", "bboost": "Bench Boost", "3xc": "Triple Captain"}

console = Console()


def m(value: int) -> str:
    """0.1m -> '£7.5m'."""
    return f"£{value / 10:.1f}m"


def _client(settings: Settings) -> FPLClient:
    return FPLClient(cache_dir=settings.cache_dir, ttl_seconds=settings.cache_ttl_seconds)


def cmd_squad(settings: Settings) -> None:
    with _client(settings) as client:
        state = load_team_state(client, settings.team_id)
        gws = gameweeks(client.bootstrap())
    print_squad(state, gws.next_deadline)


def print_squad(state: TeamState, deadline: datetime | None) -> None:
    console.rule(f"[bold]{state.team_name}[/] — {state.manager}")
    console.print(
        f"Poin total [bold]{state.overall_points}[/] | Rank global {state.overall_rank:,} | "
        f"Squad dari GW{state.gw}"
    )
    if deadline:
        console.print(
            f"Deadline GW{state.next_gw}: [bold yellow]{deadline.astimezone(WIB):%a %d %b %H:%M} WIB[/]"
        )
    console.print(
        f"Bank {m(state.bank)} | Free transfer ≈ [bold]{state.free_transfers}[/] | "
        f"Dana total (jual semua) ≈ {m(state.budget)}"
    )

    table = Table(show_lines=False)
    for col in ("#", "Pos", "Pemain", "Klub", "Harga", "Jual", "Form", "Poin", "xP next", "Status"):
        table.add_column(col)
    for p in state.players:
        name = p.name + (" (C)" if p.is_captain else " (V)" if p.is_vice else "")
        status = "" if p.status == "a" else f"[red]{p.chance_next or 0}% {p.news}[/]"
        style = "dim" if p.squad_slot > 11 else None
        table.add_row(
            str(p.squad_slot), p.position, name, p.team, m(p.now_cost), m(p.selling_price),
            f"{p.form:.1f}", str(p.total_points), f"{p.ep_next:.1f}", status, style=style,
        )
    console.print(table)

    chips = ", ".join(f"{CHIP_LABEL.get(c['name'], c['name'])} (s/d GW{c['stop_event']})" for c in state.chips_available)
    console.print(f"Chip tersedia: {chips or '-'}")
    for w in state.warnings:
        console.print(f"[yellow]⚠ {w}[/]")
    console.print("[dim]Harga jual & FT = estimasi dari data publik.[/]")


def cmd_league(settings: Settings, top: int) -> None:
    with _client(settings) as client:
        console.print("[dim]Mengambil picks semua anggota liga...[/]")
        report = load_league(client, settings.league_id)
        boot = client.bootstrap()
    me = report.entry(settings.team_id)

    console.rule(f"[bold]{report.league_name}[/] — GW{report.gw}")
    table = Table()
    for col in ("Rank", "Tim", "Manager", f"GW{report.gw}", "Total", "Gap", "Captain", "Chip"):
        table.add_column(col)
    elements = elements_by_id(boot)
    leader = report.entries[0].total if report.entries else 0
    for e in report.entries:
        cap = elements[e.captain]["web_name"] if e.captain else "-"
        style = "bold green" if e.entry_id == settings.team_id else None
        table.add_row(
            str(e.rank), e.team_name, e.manager, str(e.event_total), str(e.total),
            str(e.total - leader), cap, e.active_chip or "", style=style,
        )
    console.print(table)

    # EO lawan (tanpa tim sendiri) vs kepemilikan kita.
    rivals_eo = compute_eo(report.entries, elements, teams_by_id(boot), exclude_entry=settings.team_id)
    mine = me.multipliers if me else {}
    eo_table = Table(title=f"Top {top} EO lawan di liga (GW{report.gw})")
    for col in ("Pemain", "Klub", "Pos", "Punya%", "Main%", "Capt%", "EO", "Kamu"):
        eo_table.add_column(col)
    for p in rivals_eo[:top]:
        my_m = mine.get(p.id)
        mine_txt = "-" if my_m is None else ("bench" if my_m == 0 else f"{my_m}×")
        style = "red" if my_m is None and p.eo >= 0.5 else None
        eo_table.add_row(
            p.name, p.team, p.position, f"{p.owned_pct:.0f}", f"{p.start_pct:.0f}",
            f"{p.captain_pct:.0f}", f"{p.eo:.2f}", mine_txt, style=style,
        )
    console.print(eo_table)
    console.print("[dim]Merah = banyak dimainkan lawan tapi tidak kamu punya (risiko tertinggal).[/]")


def cmd_snapshot(settings: Settings) -> None:
    """Tulis data/state.json — dipakai GitHub Actions & dashboard nanti."""
    with _client(settings) as client:
        state = load_team_state(client, settings.team_id)
        report = load_league(client, settings.league_id)
        gws = gameweeks(client.bootstrap())
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "next_deadline": gws.next_deadline.isoformat() if gws.next_deadline else None,
        "team": asdict(state),
        "league": {
            "id": report.league_id,
            "name": report.league_name,
            "gw": report.gw,
            "standings": [
                {k: v for k, v in asdict(e).items() if k != "multipliers"} for e in report.entries
            ],
            "eo": [asdict(p) for p in report.eo],
        },
    }
    path = settings.data_dir / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"Tersimpan: {path}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fpl-assistant", description="Asisten FPL liga kantor")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("squad", help="Tampilkan squad, bank, FT, chip")
    lg = sub.add_parser("league", help="Standings liga + EO lawan")
    lg.add_argument("--top", type=int, default=25)
    sub.add_parser("snapshot", help="Simpan state ke data/state.json")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.cmd == "squad":
        cmd_squad(settings)
    elif args.cmd == "league":
        cmd_league(settings, args.top)
    elif args.cmd == "snapshot":
        cmd_snapshot(settings)
