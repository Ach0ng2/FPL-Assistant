/**
 * Cloudflare Worker: 24/7 Telegram Webhook Bot untuk FPL-Assistant.
 * 100% Gratis, Zero-Server, Respon Instan (<50ms).
 */

const KEYBOARD = {
  inline_keyboard: [
    [
      { text: "👕 Skuad & Info Tim", callback_data: "btn_squad" },
      { text: "🏆 Klasemen & EO Liga", callback_data: "btn_league" },
    ],
    [
      { text: "⚽ Rekomendasi Starting 11", callback_data: "btn_lineup" },
      { text: "🚀 Transfer Solver", callback_data: "btn_recommend" },
    ],
    [
      { text: "🎟️ Strategi Chip", callback_data: "btn_chips" },
      { text: "🃏 Simulasi Best Wildcard", callback_data: "btn_wc_squad" },
    ],
    [{ text: "🔄 Refresh Menu", callback_data: "btn_start" }],
  ],
};

const CHIPS_KEYBOARD = {
  inline_keyboard: [
    [{ text: "🃏 Simulasi Skuad Wildcard (WC)", callback_data: "btn_wc_squad" }],
    [{ text: "🔙 Kembali ke Menu Utama", callback_data: "btn_start" }],
  ],
};

function m(val) {
  return `£${(val / 10).toFixed(1)}m`;
}

function formatDate(isoStr) {
  if (!isoStr) return "-";
  try {
    const d = new Date(isoStr);
    return d.toLocaleString("id-ID", {
      timeZone: "Asia/Jakarta",
      weekday: "short",
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }) + " WIB";
  } catch {
    return isoStr;
  }
}

async function fetchState(env) {
  const url = env.GITHUB_STATE_URL || "https://raw.githubusercontent.com/Ach0ng2/FPL-Assistant/main/data/state.json";
  const res = await fetch(url, { headers: { "User-Agent": "CF-FPL-Bot" }, cf: { cacheTtl: 30 } });
  if (!res.ok) throw new Error("Gagal mengambil snapshot state.json");
  return await res.json();
}

// Formatters
function getSquadText(state) {
  const t = state.team;
  const dl = formatDate(state.next_deadline);
  let lines = [
    `⚽ *${t.team_name}* (${t.manager})`,
    `📊 Poin: *${t.overall_points}* | Rank: *${t.overall_rank?.toLocaleString() || "-"}*`,
    `💰 Sisa Bank: *${m(t.bank)}* | Free Transfer: *${t.free_transfers}*`,
    `⏰ Deadline GW${state.target_gw}: *${dl}*\n`,
    `*Daftar Skuad Saat Ini:*`,
  ];
  for (const p of t.players.slice(0, 11)) {
    const cap = p.is_captain ? " (C)" : p.is_vice ? " (V)" : "";
    const warn = p.status !== "a" ? ` ⚠️ _${p.news}_` : "";
    lines.push(`• \`${p.position}\` *${p.name}*${cap} (${p.team}) - ${m(p.now_cost)}${warn}`);
  }
  lines.push(`\n*Bench:*`);
  for (const p of t.players.slice(11)) {
    const warn = p.status !== "a" ? ` ⚠️ _${p.news}_` : "";
    lines.push(`• \`${p.position}\` ${p.name} (${p.team}) - ${m(p.now_cost)}${warn}`);
  }
  for (const w of t.warnings || []) {
    lines.push(`\n💡 _${w}_`);
  }
  return lines.join("\n");
}

function getLineupText(state) {
  const l = state.lineup;
  const t = state.team;
  const dl = formatDate(state.next_deadline);
  let lines = [
    `⚽ *SARAN STARTING 11 — GW${state.target_gw}*`,
    `Tim: *${t.team_name}*`,
    `Proyeksi Poin Skuad: *~${l.projected_points} pts*\n`,
    `🎯 *Starting 11 Pilihan AI:*`,
  ];
  for (const p of l.starting_11) {
    const cap = p.is_captain ? " *(C)*" : p.is_vice ? " *(V)*" : "";
    lines.push(`• \`${p.position}\` *${p.name}*${cap} — xP: \`${p.xp.toFixed(1)}\``);
  }
  lines.push(`\n🪑 *Bench (Cadangan):*`);
  l.bench.forEach((p, idx) => {
    lines.push(`${idx + 1}. \`${p.position}\` ${p.name} — xP: \`${p.xp.toFixed(1)}\``);
  });
  lines.push(
    `\n👑 *Captain:* *${l.captain.name}* (C)`,
    `🛡️ *Vice-Captain:* *${l.captain.vice}* (VC)`,
    `💡 Alasan: _${l.captain.reason}_\n`,
    `🧠 *Analisis Taktik AI:*`,
    `• Memaksimalkan penyerang & gelandang bernilai xP tinggi.`,
    `• Bek inti yang dipasang punya peluang nirbobol (clean sheet) tertinggi.`,
    `\n⏰ Deadline: *${dl}*`
  );
  return lines.join("\n");
}

function getLeagueText(state) {
  const lg = state.league;
  const t = state.team;
  let lines = [
    `🏆 *${lg.name}* (GW${lg.gw})`,
    `Total Peserta: ${lg.standings.length} manajer\n`,
    `*Top 5 Klasemen:*`,
  ];
  for (const e of lg.standings.slice(0, 5)) {
    lines.push(`${e.rank}. *${e.team_name}* - ${e.total} pts (GW: ${e.event_total})`);
  }
  const myEntry = lg.standings.find((e) => e.entry_id === t.team_id);
  if (myEntry) {
    const leader = lg.standings[0]?.total || 0;
    lines.push(`\n📍 *Posisi Kamu:* #${myEntry.rank} (${myEntry.total} pts, gap ${myEntry.total - leader})`);
  }
  lines.push(`\n🔥 *Top EO Lawan (Paling Mengancam):*`);
  for (const p of lg.top_rivals_eo.slice(0, 5)) {
    lines.push(`• *${p.name}* (${p.team}): EO *${p.eo.toFixed(2)}* (${p.owned_pct.toFixed(0)}% rival punya)`);
  }
  return lines.join("\n");
}

function getRecommendText(state) {
  const r = state.recommendation;
  const t = state.team;
  const dl = formatDate(state.next_deadline);
  let tf = [];
  if (r.transfers_in.length > 0) {
    for (let i = 0; i < r.transfers_in.length; i++) {
      const o = r.transfers_out[i];
      const inp = r.transfers_in[i];
      tf.push(`• 🔴 *OUT:* ${o.name} (${m(o.sell_price)}) ➡️ 🟢 *IN:* ${inp.name} (${m(inp.cost)})`);
    }
  } else {
    tf.push("• _Simpan Transfer (Roll FT)_");
  }

  let lines = [
    `🚀 *REKOMENDASI GW${state.target_gw}*`,
    `Tim: *${t.team_name}*\n`,
    `*Transfer:*`,
    ...tf,
    `\n💰 Sisa Bank: *${m(r.remaining_bank)}* | Hit: *-${r.net_cost_pts} pts*`,
    `📈 Gain xP 3 GW: *+${r.gain_xp.toFixed(1)} pts*\n`,
    `👑 *Captain:* *${state.lineup.captain.name}* (C)`,
    `🛡️ *Vice:* *${state.lineup.captain.vice}* (VC)`,
    `💡 Mode: _${state.lineup.captain.mode}_\n`,
    `🎯 *Proyeksi Poin Starting 11:* ~${state.lineup.projected_points} pts`,
    `⏰ *Deadline:* ${dl}`,
  ];
  return lines.join("\n");
}

function getChipsText(state) {
  let lines = [
    "🎟️ *STRATEGI PENGGUNAAN CHIP (PARUH 1)*",
    "⚠️ _Ingat: Semua chip paruh pertama hangus setelah GW19!_\n",
  ];
  for (const c of state.chips) {
    const badge = c.urgency === "HIGH" ? "🔴 SEGERA" : c.urgency === "MEDIUM" ? "🟡 PERTIMBANGKAN" : "🟢 SANTAI";
    lines.push(
      `📌 *${c.chip_name}* [${badge}]`,
      `• Waktu Ideal: *${c.recommended_gw}*`,
      `• Analisis: _${c.strategy_note}_\n`
    );
  }
  lines.push("💡 *Klik tombol di bawah untuk melihat simulasi skuad terbaik Wildcard!*");
  return lines.join("\n");
}

function getWildcardText(state) {
  const wc = state.wildcard_simulation;
  const gks = wc.squad.filter((p) => p.position === "GK");
  const defs = wc.squad.filter((p) => p.position === "DEF");
  const mids = wc.squad.filter((p) => p.position === "MID");
  const fwds = wc.squad.filter((p) => p.position === "FWD");

  let lines = [
    `🃏 *SIMULASI SKUAD TERBAIK WILDCARD*`,
    `Optimal untuk 5 Gameweek ke depan\n`,
    `💰 Total Biaya: *${m(wc.total_cost)}* (Sisa Bank: *${m(wc.remaining_bank)}*)`,
    `📈 Total Proyeksi xP: *~${wc.total_xp_5gw.toFixed(1)} pts*\n`,
    `🧤 *Kiper (GK):*`,
    ...gks.map((p) => `• *${p.name}* (${p.team}) - ${m(p.cost)} | xP: \`${p.total_xp.toFixed(1)}\``),
    `\n🛡️ *Bek (DEF):*`,
    ...defs.map((p) => `• *${p.name}* (${p.team}) - ${m(p.cost)} | xP: \`${p.total_xp.toFixed(1)}\``),
    `\n🎯 *Gelandang (MID):*`,
    ...mids.map((p) => `• *${p.name}* (${p.team}) - ${m(p.cost)} | xP: \`${p.total_xp.toFixed(1)}\``),
    `\n⚽ *Penyerang (FWD):*`,
    ...fwds.map((p) => `• *${p.name}* (${p.team}) - ${m(p.cost)} | xP: \`${p.total_xp.toFixed(1)}\``),
    `\n💡 Skuad di atas sudah mencakup **Haaland** untuk mengunci 91% lawan kantor!`,
  ];
  return lines.join("\n");
}

// Telegram Helpers
async function tgCall(token, method, payload) {
  return fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("FPL Telegram Webhook Worker is Active 🟢", { status: 200 });
    }

    try {
      const update = await request.json();
      const token = env.TELEGRAM_BOT_TOKEN;

      // Handle Callback Button Click
      if (update.callback_query) {
        const query = update.callback_query;
        const data = query.data;
        const msgId = query.message.message_id;
        const chatId = query.message.chat.id;

        await tgCall(token, "answerCallbackQuery", { callback_query_id: query.id });

        if (data === "btn_start") {
          await tgCall(token, "editMessageText", {
            chat_id: chatId,
            message_id: msgId,
            text: "Pilih menu di bawah ini:",
            reply_markup: KEYBOARD,
          });
          return new Response("OK");
        }

        const state = await fetchState(env);
        let text = "";
        let kb = KEYBOARD;

        if (data === "btn_squad") text = getSquadText(state);
        else if (data === "btn_lineup") text = getLineupText(state);
        else if (data === "btn_league") text = getLeagueText(state);
        else if (data === "btn_recommend") text = getRecommendText(state);
        else if (data === "btn_chips") {
          text = getChipsText(state);
          kb = CHIPS_KEYBOARD;
        } else if (data === "btn_wc_squad") text = getWildcardText(state);

        await tgCall(token, "editMessageText", {
          chat_id: chatId,
          message_id: msgId,
          text: text,
          parse_mode: "Markdown",
          reply_markup: kb,
        });

        return new Response("OK");
      }

      // Handle Text Commands (/start, /squad, /lineup, dll)
      if (update.message && update.message.text) {
        const chatId = update.message.chat.id;
        const cmd = update.message.text.trim().toLowerCase();

        if (cmd === "/start") {
          await tgCall(token, "sendMessage", {
            chat_id: chatId,
            text: "👋 *Halo Bro!*\n\nSelamat datang di *FPL Assistant Bot (Cloudflare Edition)*.\nSilakan pilih menu di bawah ini untuk cek skuad, Starting 11, atau strategi:",
            parse_mode: "Markdown",
            reply_markup: KEYBOARD,
          });
          return new Response("OK");
        }

        const state = await fetchState(env);
        let text = "";
        let kb = KEYBOARD;

        if (cmd === "/squad") text = getSquadText(state);
        else if (cmd === "/lineup") text = getLineupText(state);
        else if (cmd === "/league") text = getLeagueText(state);
        else if (cmd === "/recommend") text = getRecommendText(state);
        else if (cmd === "/chips") {
          text = getChipsText(state);
          kb = CHIPS_KEYBOARD;
        } else if (cmd === "/wildcard") text = getWildcardText(state);
        else text = "Perintah tidak dikenali. Ketik /start untuk melihat menu tombol.";

        await tgCall(token, "sendMessage", {
          chat_id: chatId,
          text: text,
          parse_mode: "Markdown",
          reply_markup: kb,
        });

        return new Response("OK");
      }

      return new Response("OK");
    } catch (err) {
      return new Response(`Error: ${err.message}`, { status: 500 });
    }
  },
};
