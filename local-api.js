/* Calculs de l'application, 100 % dans le téléphone : mêmes formules que le serveur Python (src/model.py, src/value.py, app.py).
   Les pages appellent VB.handle('/api/...') comme elles appelleraient le serveur ; rien n'est envoyé sur Internet
   (sauf, si vous le demandez, les cotes en direct de The Odds API avec votre propre clé). */
(function (root) {
  'use strict';
  const MAX_GOALS = 10;
  const DEFAULTS = { bankroll: 1000, kelly_fraction: 0.25, max_stake_pct: 3, min_edge_pct: 5 };
  const ODDS_API = 'https://api.the-odds-api.com/v4/sports';
  const ODDS_SPORTS = {
    soccer_epl: 'Premier League', soccer_spain_la_liga: 'La Liga', soccer_germany_bundesliga: 'Bundesliga',
    soccer_italy_serie_a: 'Serie A', soccer_france_ligue_one: 'Ligue 1', soccer_efl_champ: 'Championship',
    soccer_netherlands_eredivisie: 'Eredivisie', soccer_portugal_primeira_liga: 'Primeira Liga',
    soccer_japan_j_league: 'J-League', soccer_korea_kleague1: 'K League 1', soccer_china_superleague: 'Super League chinoise'
  };

  /* ---------- stockage local (localStorage si disponible, sinon mémoire) ---------- */
  const mem = {};
  const store = {
    get(k, fallback) {
      try { const v = root.localStorage.getItem(k); return v == null ? fallback : JSON.parse(v); }
      catch (e) { return k in mem ? mem[k] : fallback; }
    },
    set(k, v) {
      mem[k] = v;
      try { root.localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; }
    }
  };

  let SNAP = null;
  const fail = (msg) => { const e = new Error(msg); e.userMessage = msg; throw e; };
  const ok = (o) => Object.assign({ ok: true }, o || {});

  /* ---------- formules ---------- */
  function pmf(lam, n) { // loi de Poisson, calculée par récurrence
    const out = new Array(n + 1); out[0] = Math.exp(-lam);
    for (let k = 1; k <= n; k++) out[k] = out[k - 1] * lam / k;
    return out;
  }
  function devig(h, d, a) { const i = [1 / h, 1 / d, 1 / a], s = i[0] + i[1] + i[2]; return [i[0] / s, i[1] / s, i[2] / s]; }
  const edge = (p, o) => p * o - 1;
  function kelly(p, o, frac) { const b = o - 1; if (b <= 0) return 0; return Math.max(0, (p * b - (1 - p)) / b) * frac; }
  function grid(lh, la) {
    const ph = pmf(lh, MAX_GOALS), pa = pmf(la, MAX_GOALS); let s = 0; const g = [];
    for (let i = 0; i <= MAX_GOALS; i++) { g.push([]); for (let j = 0; j <= MAX_GOALS; j++) { const v = ph[i] * pa[j]; g[i].push(v); s += v; } }
    for (let i = 0; i <= MAX_GOALS; i++) for (let j = 0; j <= MAX_GOALS; j++) g[i][j] /= s;
    return g;
  }

  /* ---------- réglages ---------- */
  function loadSettings() { return Object.assign({}, DEFAULTS, store.get('vb_settings', {})); }
  function saveSettings(patch) {
    const lim = { bankroll: [1, 1e9], kelly_fraction: [0.01, 1], max_stake_pct: [0.1, 25], min_edge_pct: [0, 50] };
    const s = loadSettings();
    for (const k in lim) {
      if (k in patch) {
        const v = parseFloat(String(patch[k]).replace(',', '.'));
        if (!isFinite(v)) fail('Valeur invalide pour ' + k + '.');
        s[k] = Math.min(Math.max(v, lim[k][0]), lim[k][1]);
      }
    }
    store.set('vb_settings', s);
  }
  const getKey = () => store.get('vb_odds_key', '');

  /* ---------- prédiction ---------- */
  function predict(b) {
    const m = SNAP.models[b.league];
    if (!m) fail('Aucune donnée pour ce championnat.');
    if (b.home === b.away) fail('Choisissez deux équipes différentes.');
    const th = m.teams[b.home], ta = m.teams[b.away];
    if (!th || !ta) fail('Équipe inconnue du modèle pour ce championnat.');
    const lh = th[0] * ta[1] * m.avg_home, la = ta[0] * th[1] * m.avg_away;
    const g = grid(lh, la);
    let pH = 0, pD = 0, pA = 0, over = 0, btts = 0; const sc = [];
    for (let i = 0; i <= MAX_GOALS; i++) for (let j = 0; j <= MAX_GOALS; j++) {
      const v = g[i][j];
      if (i > j) pH += v; else if (i === j) pD += v; else pA += v;
      if (i + j > 2) over += v;
      if (i >= 1 && j >= 1) btts += v;
      if (i < 6 && j < 6) sc.push([i, j, v]);
    }
    sc.sort((x, y) => y[2] - x[2]);
    const res = { p: { home: pH, draw: pD, away: pA }, lam: [lh, la], scores: sc.slice(0, 5), over25: over, btts };
    const odds = [b.odds_home, b.odds_draw, b.odds_away].map(o => (o === '' || o == null) ? null : parseFloat(String(o).replace(',', '.')));
    if (odds.some(o => o !== null && isNaN(o))) fail('Les cotes doivent être des nombres (par exemple 2.10).');
    if (odds.every(o => o && o > 1)) {
      const st = loadSettings(), mk = devig(odds[0], odds[1], odds[2]), bankroll = parseFloat(b.bankroll) || st.bankroll;
      const rows = []; let best = null;
      ['home', 'draw', 'away'].forEach((k, i) => {
        const pm = [pH, pD, pA][i], e = edge(pm, odds[i]);
        rows.push({ outcome: k, odds: odds[i], market: mk[i], model: pm, edge: e });
        if (e >= st.min_edge_pct / 100 && (!best || e > best.edge)) best = { outcome: k, odds: odds[i], edge: e, p: pm };
      });
      if (best) best.stake = Math.round(bankroll * Math.min(kelly(best.p, best.odds, st.kelly_fraction), st.max_stake_pct / 100) * 100) / 100;
      res.market = { rows, margin: odds.reduce((s, o) => s + 1 / o, 0) - 1, best, bankroll };
    }
    return res;
  }

  /* ---------- comparateur de cotes ---------- */
  function compare(b) {
    let book, ref;
    try { book = b.book.map(x => parseFloat(String(x).replace(',', '.'))); ref = b.ref.map(x => parseFloat(String(x).replace(',', '.'))); } catch (e) { book = []; }
    if (!book || !ref || book.length !== 3 || ref.length !== 3 || [...book, ...ref].some(x => isNaN(x))) fail('Saisissez six cotes sous forme de nombres (par exemple 2.10).');
    if ([...book, ...ref].some(x => x <= 1)) fail('Chaque cote doit être supérieure à 1.');
    const st = loadSettings(), fair = devig(ref[0], ref[1], ref[2]), rows = []; let best = null;
    ['home', 'draw', 'away'].forEach((k, i) => {
      const e = edge(fair[i], book[i]);
      rows.push({ outcome: k, book: book[i], ref: ref[i], fair_prob: fair[i], fair_odds: 1 / fair[i], edge: e, min_odds: (1 / fair[i]) * (1 + st.min_edge_pct / 100) });
      if (e >= st.min_edge_pct / 100 && (!best || e > best.edge)) best = { outcome: k, odds: book[i], edge: e, p: fair[i] };
    });
    const bankroll = parseFloat(b.bankroll) || st.bankroll;
    if (best) best.stake = Math.round(bankroll * Math.min(kelly(best.p, best.odds, st.kelly_fraction), st.max_stake_pct / 100) * 100) / 100;
    const bm = book.reduce((s, o) => s + 1 / o, 0) - 1, rm = ref.reduce((s, o) => s + 1 / o, 0) - 1;
    return { rows, book_margin: bm, ref_margin: rm, extra_margin: bm - rm, best, bankroll, min_edge: st.min_edge_pct, ref_weak: rm > 0.05 };
  }

  /* ---------- cotes de référence : instantané + cotes en direct ---------- */
  function groupRefs(events) { // events : [{league, commence, home, away, books:{nom:[h,d,a]}}]
    return events.map(ev => {
      const names = Object.keys(ev.books);
      if (!names.length) return null;
      let odds, label;
      if (ev.books.pinnacle) { odds = ev.books.pinnacle; label = 'Pinnacle'; }
      else {
        const acc = [0, 0, 0];
        names.forEach(n => devig(...ev.books[n]).forEach((p, i) => acc[i] += p / names.length));
        odds = acc.map(p => 1 / p); label = 'Moyenne de ' + names.length + ' bookmakers (cotes sans marge)';
      }
      return { league: ev.league, commence: ev.commence, home: ev.home, away: ev.away, source: label, odds, fetched_at: ev.fetched_at };
    }).filter(Boolean);
  }
  function refMatches() {
    const live = store.get('vb_live_refs', { items: [] }).items || [];
    const cutoff = Date.now() - 36e5 * 24;
    const snap = (SNAP.ref_matches || []).filter(m => !m.commence || Date.parse(m.commence) >= cutoff);
    return live.concat(snap);
  }
  async function fetchLiveRefs(sport) {
    const key = getKey();
    if (!key) fail('Enregistrez d’abord votre clé The Odds API dans « Sources & réglages ».');
    let r;
    try {
      r = await fetch(ODDS_API + '/' + encodeURIComponent(sport) + '/odds/?' + new URLSearchParams({ apiKey: key, regions: 'eu', markets: 'h2h', oddsFormat: 'decimal' }));
    } catch (e) { fail('Connexion impossible (hors ligne, ou le navigateur a bloqué la requête). Vous pouvez saisir les cotes à la main.'); }
    if (r.status === 401 || r.status === 403) fail('Clé refusée par The Odds API.');
    if (r.status === 429) fail('Quota de The Odds API atteint pour ce mois.');
    if (!r.ok) fail('The Odds API répond avec l’erreur HTTP ' + r.status + '.');
    const left = r.headers.get('x-requests-remaining');
    const data = await r.json(), now = new Date().toISOString().slice(0, 16), evs = [];
    for (const ev of data) {
      const books = {};
      for (const bm of ev.bookmakers || []) for (const mk of bm.markets || []) {
        if (mk.key !== 'h2h') continue;
        const pr = {}; (mk.outcomes || []).forEach(o => pr[o.name] = o.price);
        const h = pr[ev.home_team], a = pr[ev.away_team], d = pr.Draw;
        if (h && a && d) books[bm.key] = [h, d, a];
      }
      evs.push({ league: sport, commence: ev.commence_time, home: ev.home_team, away: ev.away_team, books, fetched_at: now });
    }
    const items = groupRefs(evs);
    const prev = store.get('vb_live_refs', { items: [] }).items.filter(m => m.league !== sport);
    store.set('vb_live_refs', { items: prev.concat(items), at: now });
    return { count: items.length, left };
  }

  /* ---------- suivi à blanc ---------- */
  const jload = () => store.get('vb_journal', []);
  function journalList() {
    const items = jload().slice().sort((a, b) => b.id - a.id), st = loadSettings();
    let profit = 0, staked = 0, settled = 0, won = 0;
    for (const it of items) {
      if (it.result === 'won') { profit += it.stake * (it.odds - 1); staked += it.stake; settled++; won++; }
      else if (it.result === 'lost') { profit -= it.stake; staked += it.stake; settled++; }
    }
    return { items, summary: { start: st.bankroll, current: st.bankroll + profit, profit, staked, settled, won,
      pending: items.filter(i => i.result === 'pending').length, roi: staked ? profit / staked : null } };
  }
  function journalAdd(b) {
    const odds = parseFloat(String(b.odds).replace(',', '.')), stake = parseFloat(String(b.stake).replace(',', '.'));
    if (isNaN(odds) || isNaN(stake)) fail('Cote et mise sont obligatoires.');
    if (odds <= 1 || stake <= 0) fail('La cote doit être supérieure à 1 et la mise positive.');
    const j = jload(), id = (store.get('vb_journal_seq', 0) || 0) + 1;
    j.push({ id, ts: new Date().toISOString().slice(0, 16), league: b.league || null, home: b.home || null, away: b.away || null,
      pick: b.pick || '', odds, stake, p_model: b.p_model == null ? null : b.p_model, result: 'pending', note: b.note || '' });
    store.set('vb_journal_seq', id); store.set('vb_journal', j);
  }
  function journalSettle(id, result) {
    if (!['won', 'lost', 'pending'].includes(result)) fail('Résultat invalide.');
    store.set('vb_journal', jload().map(i => i.id === id ? Object.assign({}, i, { result }) : i));
  }
  const journalDelete = (id) => store.set('vb_journal', jload().filter(i => i.id !== id));
  function journalImport(items) {
    if (!Array.isArray(items)) fail('Fichier de sauvegarde invalide.');
    const clean = items.filter(i => i && isFinite(i.odds) && isFinite(i.stake)).map((i, n) => Object.assign({}, i, { id: n + 1, result: ['won', 'lost', 'pending'].includes(i.result) ? i.result : 'pending' }));
    store.set('vb_journal', clean); store.set('vb_journal_seq', clean.length);
    return clean.length;
  }

  /* ---------- routeur : mêmes adresses que le serveur Python ---------- */
  async function handle(url, opt) {
    opt = opt || {};
    const method = (opt.method || 'GET').toUpperCase();
    const body = opt.body ? JSON.parse(opt.body) : {};
    let m;
    try {
      if (!SNAP) await loadSnapshot();
      if (url === '/api/status') {
        const c = Object.assign({}, SNAP.counts, { journal: jload().length });
        return ok({ counts: c, newest: SNAP.newest, generated: SNAP.generated, last: [], upcoming: SNAP.upcoming || [], lineup: SNAP.lineup || {} });
      }
      if (url === '/api/leagues') return ok({ leagues: SNAP.leagues });
      if ((m = url.match(/^\/api\/teams\/(.+)$/))) return ok({ teams: Object.keys((SNAP.models[m[1]] || { teams: {} }).teams).sort((a, b) => a.localeCompare(b)) });
      if (url === '/api/predict') return ok(predict(body));
      if (url === '/api/ref_matches') return ok({ matches: refMatches() });
      if (url === '/api/compare') return ok(compare(body));
      if (url === '/api/formations') return ok({ globales: SNAP.formations.globales, duels: SNAP.formations.duels, equipes: SNAP.formations.equipes });
      if (url === '/api/results') return ok({ leagues: SNAP.results_leagues, lineup: SNAP.lineup || {} });
      if (url === '/api/journal' && method === 'GET') return ok(journalList());
      if (url === '/api/journal' && method === 'POST') { journalAdd(body); return ok(); }
      if ((m = url.match(/^\/api\/journal\/(\d+)$/))) {
        if (method === 'DELETE') { journalDelete(+m[1]); return ok(); }
        journalSettle(+m[1], body.result); return ok();
      }
      if (url === '/api/sources') return ok({ sources: SNAP.sources || [], settings: loadSettings(), odds_key_set: !!getKey() });
      if (url === '/api/settings') {
        if (body.ODDS_API_KEY != null) store.set('vb_odds_key', String(body.ODDS_API_KEY).trim());
        saveSettings(body); return ok();
      }
      fail('Adresse inconnue : ' + url);
    } catch (e) { return { ok: false, error: e.userMessage || e.message || 'Erreur' }; }
  }

  async function loadSnapshot(force) {
    const r = await fetch('data/snapshot.json', force ? { cache: 'reload' } : undefined);
    if (!r.ok) throw new Error('Données introuvables (' + r.status + ').');
    SNAP = await r.json();
    return SNAP;
  }

  const VB = { handle, loadSnapshot, setSnapshot(s) { SNAP = s; }, predict, compare, devig, grid, groupRefs, fetchLiveRefs,
    journalExport: () => jload(), journalImport, getKey, store, ODDS_SPORTS, snapshot: () => SNAP };
  if (typeof module !== 'undefined' && module.exports) module.exports = VB; else root.VB = VB;
})(typeof self !== 'undefined' ? self : this);
