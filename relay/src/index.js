/**
 * Relais RSPS — Cloudflare Worker.
 *
 *   POST /hook/<SECRET>  alerte TradingView (JSON émis par RSPS_Relais.pine)
 *   GET  /state          état combiné (même format que docs/state.json) + source "tradingview"
 *   GET  /log            dernières alertes reçues
 *
 * KV `RSPS` : "sys:<SYS>|<TF>" (dernière alerte par système/timeframe), "state", "log".
 * Règles du classeur (identiques à strategy.py) : LONG si MTPI > 0,1, CASH si < 0,1 (0,1 pile :
 * inchangé) ; ETH majeur si rotation > 0 ; trash = 20 % × force si LONG et OTHERS.D > 0.
 */
const THRESHOLD = 0.10, TRASH_MAX = 0.20;
const SYSTEMS = ["MTPI", "ROT", "TRASH"];
const STATES_KEY = { MTPI: "states", ROT: "rot_states", TRASH: "trash_states" };
const LOG_MAX = 500;

const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS" };
const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj, null, 2), {
    status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...CORS },
  });

function safeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

/** Valide et normalise une alerte ; renvoie [alerte, null] ou [null, erreur]. */
export function parseAlert(body) {
  let a;
  try { a = typeof body === "string" ? JSON.parse(body) : body; } catch { return [null, "JSON invalide"]; }
  if (!a || typeof a !== "object") return [null, "JSON invalide"];
  const sys = String(a.sys || "").toUpperCase();
  if (!SYSTEMS.includes(sys)) return [null, `sys inconnu : ${a.sys}`];
  const tf = String(a.tf || "").toUpperCase().slice(0, 6);
  if (!/^[0-9]*[DWM]?$/.test(tf) || !tf) return [null, `tf invalide : ${a.tf}`];
  const time = Number(a.time);
  if (!Number.isFinite(time) || time < 1.2e12 || time > 5e12) return [null, "time invalide (ms attendues)"];
  const states = {};
  const entries = Object.entries(a.states || {});
  if (!entries.length || entries.length > 20) return [null, "states : 1 à 20 indicateurs attendus"];
  for (const [k, v] of entries) {
    const n = Number(v);
    if (![-1, 0, 1].includes(n)) return [null, `état invalide pour ${k} : ${v}`];
    states[String(k).slice(0, 60)] = n;
  }
  return [{ sys, tf, time, ticker: String(a.ticker || "").slice(0, 40), states }, null];
}

const mean = (xs) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null);
const r4 = (x) => (x == null ? null : Math.round(x * 1e4) / 1e4);
const day = (ms) => new Date(ms - 1).toISOString().slice(0, 10);   // dernier jour de la bougie

/** Combine les dernières alertes de chaque système/TF en un état unique. */
export function combine(alerts, prevRegime) {
  const bySys = {};
  for (const a of alerts) (bySys[a.sys] ||= []).push(a);
  const out = { source: "tradingview", systems: {} };
  let last = 0;
  for (const sys of SYSTEMS) {
    const list = bySys[sys] || [];
    const states = Object.assign({}, ...list.map((a) => a.states));
    out[STATES_KEY[sys]] = states;
    out.systems[sys] = {
      score: r4(mean(Object.values(states))),
      tfs: Object.fromEntries(list.map((a) => [a.tf, { time: a.time, date: day(a.time), ticker: a.ticker, states: a.states }])),
    };
    for (const a of list) last = Math.max(last, a.time);
  }
  const mtpi = out.systems.MTPI.score, rot = out.systems.ROT.score, trash = out.systems.TRASH.score;
  let regime = prevRegime || "CASH";
  if (mtpi != null) regime = mtpi > THRESHOLD ? "LONG" : mtpi < THRESHOLD ? "CASH" : regime;
  const long = regime === "LONG", ethOver = rot != null && rot > 0, small = long && trash != null && trash > 0;
  const trashPct = small ? r4(TRASH_MAX * trash) : 0;
  let alloc = long ? (ethOver ? "LONG · ETH 80 / BTC 20" : "LONG · BTC 80 / ETH 20") : "CASH · Dominant Denominator";
  if (small) alloc += `  + trash ${Math.round(trashPct * 100)}%`;
  return Object.assign(out, {
    date: last ? day(last) : null,
    mtpi, regime, rotation: rot, majeur: ethOver ? "ETH" : "BTC",
    trash, small_caps: small, trash_pct: trashPct, alloc,
  });
}

async function notify(env, msg) {
  if (!env.TG_TOKEN || !env.TG_CHAT) return;
  await fetch(`https://api.telegram.org/bot${env.TG_TOKEN}/sendMessage`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id: env.TG_CHAT, text: msg, parse_mode: "HTML" }),
  }).catch(() => {});
}

async function loadAlerts(env) {
  const keys = (await env.RSPS.list({ prefix: "sys:" })).keys;
  return (await Promise.all(keys.map((k) => env.RSPS.get(k.name, "json")))).filter(Boolean);
}

async function handleHook(req, env) {
  const text = await req.text();
  if (text.length > 8000) return json({ ok: false, error: "corps trop gros" }, 413);
  const [a, err] = parseAlert(text);
  if (err) return json({ ok: false, error: err }, 400);
  a.received = Date.now();
  await env.RSPS.put(`sys:${a.sys}|${a.tf}`, JSON.stringify(a));

  const prev = (await env.RSPS.get("state", "json")) || {};
  const alerts = (await loadAlerts(env)).filter((x) => !(x.sys === a.sys && x.tf === a.tf)).concat(a);
  const state = combine(alerts, prev.regime);
  state.updated = new Date().toISOString();
  await env.RSPS.put("state", JSON.stringify(state));

  const log = (await env.RSPS.get("log", "json")) || [];
  log.unshift({ t: a.received, sys: a.sys, tf: a.tf, date: day(a.time),
                score: r4(mean(Object.values(a.states))), regime: state.regime });
  await env.RSPS.put("log", JSON.stringify(log.slice(0, LOG_MAX)));

  if (prev.regime && prev.regime !== state.regime) {
    await notify(env, `♻️ <b>RÉGIME CHANGE</b> (TradingView)\n${state.regime === "LONG" ? "🟢" : "🔴"} <b>${state.regime}</b> · MTPI ${state.mtpi}\nAllocation : <b>${state.alloc}</b>`);
  }
  return json({ ok: true, regime: state.regime, mtpi: state.mtpi });
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (req.method === "POST" && url.pathname.startsWith("/hook/")) {
      if (!env.HOOK_SECRET || !safeEqual(url.pathname.slice(6), env.HOOK_SECRET)) return json({ ok: false }, 403);
      return handleHook(req, env);
    }
    if (req.method === "GET" && url.pathname === "/state") {
      // recalcul à la lecture : deux alertes simultanées (MTPI 2D + 3D) peuvent
      // se croiser au moment de l'écriture, la KV étant à cohérence différée.
      const prev = (await env.RSPS.get("state", "json")) || {};
      const alerts = await loadAlerts(env);
      if (!alerts.length) return json({ source: "tradingview", date: null, systems: {} });
      return json({ ...combine(alerts, prev.regime), updated: prev.updated });
    }
    if (req.method === "GET" && url.pathname === "/log") {
      return json((await env.RSPS.get("log", "json")) || []);
    }
    return json({ ok: true, service: "rsps-relay", endpoints: ["/state", "/log"] });
  },
};
