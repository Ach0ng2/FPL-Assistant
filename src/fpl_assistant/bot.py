"""Interactive Telegram Bot Handler dengan tombol Inline Keyboard dan Command."""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from .api import FPLClient
from .bootstrap import elements_by_id, gameweeks, teams_by_id
from .captain import select_best_lineup
from .config import Settings, get_settings
from .league import compute_eo, load_league
from .optimizer import solve_transfers
from .squad import load_team_state
from .xp import PlayerXP, compute_all_xp

WIB = timezone(timedelta(hours=7))


def m(val: int) -> str:
    return f"£{val / 10:.1f}m"


def get_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("👕 Skuad & Info Tim", callback_data="btn_squad"),
            InlineKeyboardButton("🏆 Klasemen & EO Liga", callback_data="btn_league"),
        ],
        [
            InlineKeyboardButton("⚽ Rekomendasi Starting 11", callback_data="btn_lineup"),
            InlineKeyboardButton("🚀 Transfer Solver", callback_data="btn_recommend"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh Menu", callback_data="btn_start"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def format_squad_message(settings: Settings) -> str:
    with FPLClient(cache_dir=settings.cache_dir, ttl_seconds=settings.cache_ttl_seconds) as client:
        state = load_team_state(client, settings.team_id)
        gws = gameweeks(client.bootstrap())

    dl_str = gws.next_deadline.astimezone(WIB).strftime("%a %d %b %H:%M WIB") if gws.next_deadline else "-"

    lines = [
        f"⚽ *{state.team_name}* ({state.manager})",
        f"📊 Poin: *{state.overall_points}* | Rank: *{state.overall_rank:,}*",
        f"💰 Sisa Bank: *{m(state.bank)}* | Free Transfer: *{state.free_transfers}*",
        f"⏰ Deadline GW{state.next_gw}: *{dl_str}*\n",
        "*Daftar Skuad Saat Ini:*",
    ]

    for p in state.players[:11]:
        cap = " (C)" if p.is_captain else " (V)" if p.is_vice else ""
        status_alert = f" ⚠️ _{p.news}_" if p.status != "a" else ""
        lines.append(f"• `{p.position}` *{p.name}*{cap} ({p.team}) - {m(p.now_cost)}{status_alert}")

    lines.append("\n*Bench:*")
    for p in state.players[11:]:
        status_alert = f" ⚠️ _{p.news}_" if p.status != "a" else ""
        lines.append(f"• `{p.position}` {p.name} ({p.team}) - {m(p.now_cost)}{status_alert}")

    for w in state.warnings:
        lines.append(f"\n💡 _{w}_")

    chips = ", ".join(c["name"] for c in state.chips_available if c["stop_event"] <= 19)
    lines.append(f"\n🎟️ Chip Paruh 1: `{chips or 'Habis'}`")

    return "\n".join(lines)


def format_lineup_message(settings: Settings) -> str:
    with FPLClient(cache_dir=settings.cache_dir, ttl_seconds=settings.cache_ttl_seconds) as client:
        boot = client.bootstrap()
        fixtures = client.fixtures()
        gws = gameweeks(boot)
        target_gw = gws.next or 10

        state = load_team_state(client, settings.team_id)
        report = load_league(client, settings.league_id)

    all_xp = compute_all_xp(boot, fixtures, [target_gw])
    current_squad_xp = [all_xp[p.id] for p in state.players if p.id in all_xp]

    lineup = select_best_lineup(current_squad_xp, target_gw, report.eo, chasing=True)
    cap = lineup.captain_advice

    dl_str = gws.next_deadline.astimezone(WIB).strftime("%a %d %b %H:%M WIB") if gws.next_deadline else "-"

    lines = [
        f"⚽ *SARAN STARTING 11 — GW{target_gw}*",
        f"Tim: *{state.team_name}*",
        f"Proyeksi Poin Skuad: *~{lineup.projected_points:.1f} pts*\n",
        "🎯 *Starting 11 Pilihan AI:*",
    ]

    for p in lineup.starting_11:
        c_mark = " *(C)*" if p.element_id == cap.captain.element_id else " *(V)*" if p.element_id == cap.vice_captain.element_id else ""
        lines.append(f"• `{p.position}` *{p.web_name}*{c_mark} — xP: `{p.xp_by_gw.get(target_gw, 0):.1f}`")

    lines.append("\n🪑 *Bench (Cadangan):*")
    for idx, p in enumerate(lineup.bench, 1):
        lines.append(f"{idx}. `{p.position}` {p.web_name} — xP: `{p.xp_by_gw.get(target_gw, 0):.1f}`")

    lines.extend([
        f"\n👑 *Captain:* *{cap.captain.web_name}* (C)",
        f"🛡️ *Vice-Captain:* *{cap.vice_captain.web_name}* (VC)",
        f"💡 Alasan: _{cap.reason}_",
        f"\n⏰ Deadline: *{dl_str}*",
    ])
    return "\n".join(lines)


def format_league_message(settings: Settings) -> str:
    with FPLClient(cache_dir=settings.cache_dir, ttl_seconds=settings.cache_ttl_seconds) as client:
        report = load_league(client, settings.league_id)
        boot = client.bootstrap()

    elements = elements_by_id(boot)
    teams = teams_by_id(boot)
    leader_pts = report.entries[0].total if report.entries else 0

    lines = [
        f"🏆 *{report.league_name}* (GW{report.gw})",
        f"Total Peserta: {len(report.entries)} manajer\n",
        "*Top 5 Klasemen:*",
    ]

    for e in report.entries[:5]:
        lines.append(f"{e.rank}. *{e.team_name}* - {e.total} pts (GW: {e.event_total})")

    my_entry = report.entry(settings.team_id)
    if my_entry:
        gap = my_entry.total - leader_pts
        lines.append(f"\n📍 *Posisi Kamu:* #{my_entry.rank} ({my_entry.total} pts, gap {gap})")

    rivals_eo = compute_eo(report.entries, elements, teams, exclude_entry=settings.team_id)
    lines.append("\n🔥 *Top EO Lawan (Paling Mengancam):*")
    for p in rivals_eo[:5]:
        lines.append(f"• *{p.name}* ({p.team}): EO *{p.eo:.2f}* ({p.owned_pct:.0f}% rival punya)")

    return "\n".join(lines)


def format_recommend_message(settings: Settings) -> str:
    with FPLClient(cache_dir=settings.cache_dir, ttl_seconds=settings.cache_ttl_seconds) as client:
        boot = client.bootstrap()
        fixtures = client.fixtures()
        gws = gameweeks(boot)
        target_gw = gws.next or 10
        horizon_gws = list(range(target_gw, target_gw + 3))

        state = load_team_state(client, settings.team_id)
        report = load_league(client, settings.league_id)

    all_xp = compute_all_xp(boot, fixtures, horizon_gws)
    plan = solve_transfers(
        state=state,
        all_xp=all_xp,
        bootstrap=boot,
        horizon_gws=horizon_gws,
        max_transfers_to_consider=2,
    )
    lineup = select_best_lineup(plan.new_squad, target_gw, report.eo, chasing=True)
    cap = lineup.captain_advice

    tf_lines = []
    if plan.transfers_in:
        for o, i in zip(plan.transfers_out, plan.transfers_in):
            tf_lines.append(f"• 🔴 *OUT:* {o['name']} ({m(o['sell_price'])}) ➡️ 🟢 *IN:* {i.web_name} ({m(i.now_cost)})")
    else:
        tf_lines.append("• _Simpan Transfer (Roll FT)_")

    dl_str = gws.next_deadline.astimezone(WIB).strftime("%a %d %b %H:%M WIB") if gws.next_deadline else "-"

    lines = [
        f"🚀 *REKOMENDASI GW{target_gw}*",
        f"Tim: *{state.team_name}*\n",
        "*Transfer:*",
        *tf_lines,
        f"\n💰 Sisa Bank: *{m(plan.remaining_bank)}* | Hit: *-{plan.net_cost_pts} pts*",
        f"📈 Gain xP 3 GW: *+{plan.expected_gain_xp:.1f} pts*\n",
        f"👑 *Captain:* *{cap.captain.web_name}* (C)",
        f"🛡️ *Vice:* *{cap.vice_captain.web_name}* (VC)",
        f"💡 Mode: _{cap.captain_mode}_\n",
        f"🎯 *Proyeksi Poin Starting 11:* ~{lineup.projected_points:.1f} pts",
        f"⏰ *Deadline:* {dl_str}",
    ]
    return "\n".join(lines)


# ---------- Command Handlers ----------


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 *Halo Bro!*\n\n"
        "Selamat datang di *FPL Assistant Bot*.\n"
        "Silakan pilih menu di bawah ini untuk cek skuad, saran Starting 11, posisi liga, atau optimasi transfer:"
    )
    keyboard = get_menu_keyboard()
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


async def squad_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    msg = await update.message.reply_text("⏳ _Mengambil data skuad..._", parse_mode=ParseMode.MARKDOWN)
    text = await asyncio.to_thread(format_squad_message, settings)
    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_menu_keyboard())


async def lineup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    msg = await update.message.reply_text("⏳ _Menghitung formasi Starting 11 terbaik..._", parse_mode=ParseMode.MARKDOWN)
    text = await asyncio.to_thread(format_lineup_message, settings)
    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_menu_keyboard())


async def league_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    msg = await update.message.reply_text("⏳ _Menganalisis rival liga kantor..._", parse_mode=ParseMode.MARKDOWN)
    text = await asyncio.to_thread(format_league_message, settings)
    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_menu_keyboard())


async def recommend_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    msg = await update.message.reply_text("⏳ _Menghitung optimasi transfer & kapten..._", parse_mode=ParseMode.MARKDOWN)
    text = await asyncio.to_thread(format_recommend_message, settings)
    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_menu_keyboard())


# ---------- Button Callback Handler ----------


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    settings = get_settings()

    if data == "btn_start":
        await query.edit_message_text(
            "Pilih menu di bawah ini:",
            reply_markup=get_menu_keyboard(),
        )
    elif data == "btn_squad":
        await query.edit_message_text("⏳ _Memuat data skuad..._", parse_mode=ParseMode.MARKDOWN)
        text = await asyncio.to_thread(format_squad_message, settings)
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_menu_keyboard())
    elif data == "btn_lineup":
        await query.edit_message_text("⏳ _Menganalisis Starting 11 terbaik skuad saat ini..._", parse_mode=ParseMode.MARKDOWN)
        text = await asyncio.to_thread(format_lineup_message, settings)
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_menu_keyboard())
    elif data == "btn_league":
        await query.edit_message_text("⏳ _Memuat klasemen liga kantor..._", parse_mode=ParseMode.MARKDOWN)
        text = await asyncio.to_thread(format_league_message, settings)
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_menu_keyboard())
    elif data == "btn_recommend":
        await query.edit_message_text("⏳ _Menghitung strategi transfer optimal..._", parse_mode=ParseMode.MARKDOWN)
        text = await asyncio.to_thread(format_recommend_message, settings)
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_menu_keyboard())


def run_bot() -> None:
    settings = get_settings()
    if not settings.telegram_token:
        print("[Error] TELEGRAM_BOT_TOKEN belum diset di environment!")
        return

    print("[INFO] FPL Assistant Telegram Bot sedang berjalan...")
    app = Application.builder().token(settings.telegram_token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("squad", squad_command))
    app.add_handler(CommandHandler("lineup", lineup_command))
    app.add_handler(CommandHandler("league", league_command))
    app.add_handler(CommandHandler("recommend", recommend_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    app.run_polling()
