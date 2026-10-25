/* Rubik's Cube Race front end. Plain JS, no build step.
   The browser never sees the API key: it only talks to the FastAPI backend. */

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (path, opts = {}) => {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
};
const fmtClock = (ms) => {
  if (ms == null || !isFinite(ms)) return "0:00.0";
  const t = Math.max(0, ms) / 1000;
  return `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, "0")}`;
};
const na = (v, digits = 1, suffix = "") => (v == null ? "N/A" : `${Number(v).toFixed(digits)}${suffix}`);

const S = {
  config: null,
  runs: [],
  race: { run: null, game: 0, tau: 0, playing: false, speed: 2, raf: null, last: 0,
          live: false, poll: null, liveGame: -1, liveStart: 0 },
};

/* ------------------------------------------------------------------ cube net */
// Net layout on a 12 x 9 grid: U above F, then L F R B, D below F.
const NET_ORIGIN = { U: [0, 3], L: [3, 0], F: [3, 3], R: [3, 6], B: [3, 9], D: [6, 3] };
const FACE_ORDER = "URFDLB";
function netHTML(state) {
  const cells = [];
  for (let f = 0; f < 6; f++) {
    const face = FACE_ORDER[f];
    const [r0, c0] = NET_ORIGIN[face];
    for (let i = 0; i < 9; i++) {
      const r = r0 + Math.floor(i / 3) + 1, c = c0 + (i % 3) + 1;
      cells.push(`<i data-c="${state[f * 9 + i]}" style="grid-row:${r};grid-column:${c}"></i>`);
    }
  }
  return cells.join("");
}

/* ------------------------------------------------------------------ runs list */
function runLabel(r) {
  const when = r.created_utc.replace("T", " ").slice(0, 16);
  return `${r.tier} · ${r.games} puzzle${r.games === 1 ? "" : "s"} · ${when} UTC · ${r.status} · $${(r.cost_usd || 0).toFixed(4)}`;
}
function defaultRun(tier = "primary") {
  const done = S.runs.filter((r) => r.status === "completed" && r.mode === "live");
  return (done.find((r) => r.tier === tier) || done[0] || S.runs[0] || {}).id;
}
async function refreshRuns() {
  S.runs = await api("/api/runs");
  for (const id of ["#replay-run", "#dash-run", "#slide-run"]) {
    const sel = $(id);
    const keep = sel.value;
    sel.innerHTML = S.runs.length
      ? S.runs.map((r) => `<option value="${esc(r.id)}">${esc(runLabel(r))}</option>`).join("")
      : `<option value="">No saved runs yet</option>`;
    sel.value = S.runs.some((r) => r.id === keep) ? keep : (defaultRun() || "");
  }
  await fillStartPuzzles();
}
async function fillStartPuzzles() {
  const id = $("#replay-run").value;
  const sel = $("#replay-start");
  if (!id) { sel.innerHTML = ""; return; }
  const run = await api(`/api/runs/${id}`);
  sel.innerHTML = run.games.map((g, i) =>
    `<option value="${i}">${i + 1}. ${esc(g.puzzle.id)}${g.repeat ? ` (repeat ${g.repeat + 1})` : ""}</option>`).join("");
}

/* ------------------------------------------------------------------ race view */
function buildCards() {
  $("#race-grid").innerHTML = S.config.models.map((m) => `
    <article class="card" id="card-${m.key}">
      <div class="card__head">
        <span class="card__name">${esc(m.name)}</span>
        <span class="badge ${m.api === "chat" ? "badge--llm" : ""}">${m.api === "chat" ? "Frontier LLM" : "Decision model"}</span>
        <span class="status" id="st-${m.key}">WAITING</span>
        <span class="rank" id="rk-${m.key}"></span>
      </div>
      <div class="card__cube"><div class="net net--big" id="net-${m.key}"></div></div>
      <div class="card__body">
        <div class="now">
          <div class="now__move" id="mv-${m.key}">—</div>
          <div><div class="now__label">Current move</div><div class="note" id="nt-${m.key}">${esc(m.id)}</div></div>
        </div>
        <div class="stats">
          <div class="stat"><div class="stat__k">Time</div><div class="stat__v" id="tm-${m.key}">0:00.0</div></div>
          <div class="stat"><div class="stat__k">Moves</div><div class="stat__v" id="mc-${m.key}">0 / ${S.config.rules.max_moves}</div></div>
          <div class="stat"><div class="stat__k">Last latency</div><div class="stat__v" id="lt-${m.key}">—</div></div>
          <div class="stat"><div class="stat__k">Avg latency</div><div class="stat__v" id="al-${m.key}">—</div></div>
        </div>
        <div class="history" id="hs-${m.key}"></div>
      </div>
    </article>`).join("");
}

function chip(step) {
  if (step.outcome === "malformed") return `<span class="chip chip--bad" title="${esc(step.error)}">✕</span>`;
  if (step.outcome === "error") return `<span class="chip chip--err" title="${esc(step.error)}">ERR</span>`;
  return `<span class="chip ${step.was_optimal ? "chip--opt" : ""}">${esc(step.move)}</span>`;
}

function renderGame(run, gi, tau, live) {
  const game = run.games[gi];
  if (!game) return;
  const pz = game.puzzle;
  const maxMoves = run.rules.max_moves;
  $("#start-net").innerHTML = netHTML(pz.state);
  $("#pz-kicker").textContent =
    `${run.tier} tier · puzzle ${gi + 1} of ${run.games.length}${live ? " · LIVE" : " · replay"}`;
  $("#pz-title").textContent = `${pz.id}${game.repeat ? ` (repeat ${game.repeat + 1})` : ""}`;
  $("#pz-scramble").innerHTML = `Scramble <b>${esc(pz.scramble.join(" "))}</b>`;
  $("#pz-optimal").innerHTML = pz.shortest_distance != null
    ? `Exact shortest solution <b>${pz.shortest_distance} moves</b> · ${esc(pz.shortest_solution.join(" "))}`
    : `Exact shortest solution: beyond exact search (extension tier)`;
  $("#spend").textContent =
    `spend $${(run.spend.reported_cost_usd || 0).toFixed(4)} · ${run.spend.turns} turns`;

  const finishes = [];
  for (const m of S.config.models) {
    const t = game.trials[m.key];
    const steps = live ? t.steps : t.steps.filter((s) => s.t_end_ms <= tau);
    const done = live ? ["solved", "out_of_moves", "aborted"].includes(t.status)
                      : (steps.length === t.steps.length && t.status !== "pending");
    const status = done ? t.status : (live ? t.status : (t.status === "pending" ? "pending" : "playing"));
    const last = steps[steps.length - 1];
    const state = last ? last.state_after : pz.state;

    $(`#net-${m.key}`).innerHTML = netHTML(state);
    const mv = $(`#mv-${m.key}`);
    mv.textContent = last ? (last.outcome === "ok" ? last.move : last.outcome === "malformed" ? "✕" : "ERR") : "—";
    mv.classList.toggle("is-bad", !!last && last.outcome !== "ok");

    const finishMs = t.steps.length ? t.steps[t.steps.length - 1].t_end_ms : 0;
    let clock;
    if (done) clock = live ? t.elapsed_ms : finishMs;
    else if (live) clock = t.status === "playing" ? Date.now() - S.race.liveStart : 0;
    else clock = status === "playing" ? tau : 0;
    $(`#tm-${m.key}`).textContent = fmtClock(clock);
    $(`#mc-${m.key}`).textContent = `${steps.length} / ${maxMoves}`;
    const lats = steps.map((s) => s.latency_ms).filter((x) => x != null);
    $(`#lt-${m.key}`).textContent = last && last.latency_ms != null ? `${Math.round(last.latency_ms)} ms` : "—";
    $(`#al-${m.key}`).textContent = lats.length ? `${Math.round(lats.reduce((a, b) => a + b, 0) / lats.length)} ms` : "—";
    $(`#hs-${m.key}`).innerHTML = steps.map(chip).join("");

    let note = m.id;
    if (last) {
      if (last.outcome !== "ok") note = last.error || last.outcome;
      else if (last.confidence != null) note = `confidence ${(last.confidence * 100).toFixed(0)}%`;
      else if (last.reasoning_tokens != null) note = `${last.reasoning_tokens} reasoning tokens`;
      if (last.distance_before != null && last.outcome === "ok") {
        note += last.was_optimal ? " · optimal move" : " · not optimal";
      }
    }
    $(`#nt-${m.key}`).textContent = note;

    const st = $(`#st-${m.key}`);
    const label = { solved: "SOLVED", out_of_moves: "MOVE LIMIT", aborted: "ABORTED",
                    playing: "THINKING", pending: "WAITING" }[status] || status.toUpperCase();
    st.textContent = label;
    st.className = "status " + ({ solved: "status--solved", out_of_moves: "status--out",
                                  aborted: "status--aborted", playing: "status--playing" }[status] || "");
    const card = $(`#card-${m.key}`);
    card.classList.toggle("is-playing", status === "playing");
    card.classList.toggle("is-solved", status === "solved");
    card.classList.toggle("is-out", status === "out_of_moves");
    if (status === "solved") finishes.push([m.key, live ? t.elapsed_ms : finishMs]);
  }
  finishes.sort((a, b) => a[1] - b[1]);
  for (const m of S.config.models) {
    const i = finishes.findIndex((f) => f[0] === m.key);
    $(`#rk-${m.key}`).textContent = i >= 0 ? ["1st", "2nd", "3rd", "4th"][i] : "";
  }
}

function gameEnd(run, gi) {
  let end = 0;
  for (const t of Object.values(run.games[gi].trials)) {
    if (t.steps.length) end = Math.max(end, t.steps[t.steps.length - 1].t_end_ms);
  }
  return end;
}

function setRaceState(text, cls) {
  const el = $("#race-state");
  el.textContent = text;
  el.className = "race-state " + (cls || "");
}

/* replay ------------------------------------------------------------------ */
async function startReplay() {
  stopReplay();
  const id = $("#replay-run").value;
  if (!id) return;
  const run = await api(`/api/runs/${id}`);
  Object.assign(S.race, { run, game: Number($("#replay-start").value || 0), tau: 0,
                          playing: true, speed: Number($("#replay-speed").value), last: performance.now(), hold: 0 });
  setRaceState("RACING", "is-running");
  S.race.raf = requestAnimationFrame(tick);
}
function stopReplay() {
  S.race.playing = false;
  if (S.race.raf) cancelAnimationFrame(S.race.raf);
  S.race.raf = null;
}
function tick(now) {
  const R = S.race;
  if (!R.playing) return;
  const dt = now - R.last;
  R.last = now;
  const end = gameEnd(R.run, R.game);
  if (R.tau < end) {
    R.tau = Math.min(end, R.tau + dt * R.speed);
    setRaceState("RACING", "is-running");
  } else {
    R.hold += dt;                                  // completion stage stays on screen
    setRaceState(R.game + 1 < R.run.games.length ? "PUZZLE COMPLETE" : "RACE COMPLETE", "is-done");
    if (R.hold > 2500 && R.game + 1 < R.run.games.length) {
      R.game += 1; R.tau = 0; R.hold = 0;
    } else if (R.hold > 2500) {
      R.playing = false;
    }
  }
  $("#race-clock").textContent = fmtClock(R.tau);
  renderGame(R.run, R.game, R.tau, false);
  if (R.playing) R.raf = requestAnimationFrame(tick);
}

/* live -------------------------------------------------------------------- */
async function startLive() {
  const body = { tier: $("#live-tier").value, puzzles: Number($("#live-puzzles").value) || null,
                 repeats: Number($("#live-repeats").value) || 1 };
  let plan;
  try { plan = await api("/api/plan", { method: "POST", body: JSON.stringify(body) }); }
  catch (e) { alert(e.message); return; }
  const r = S.config.rules;
  const ok = confirm(
    `Start a LIVE benchmark? This makes paid OpenRouter calls.\n\n` +
    `${plan.tier} tier: ${plan.puzzles} puzzle(s) x ${plan.repeats} repeat(s) x 4 models\n` +
    `Move limit ${r.max_moves} | timeout ${r.timeout_seconds}s | retries ${r.max_retries}\n` +
    `Upper bound: ${plan.max_http_calls_total} HTTP calls\n` +
    `Run budget: stops new calls once reported spend reaches $${plan.run_budget_usd.toFixed(2)}`);
  if (!ok) return;
  let started;
  try { started = await api("/api/runs", { method: "POST", body: JSON.stringify({ ...body, confirm: true }) }); }
  catch (e) { alert(e.message); return; }
  stopReplay();
  Object.assign(S.race, { live: true, liveGame: -1, run: null, id: started.id });
  $("#live-abort").disabled = false;
  $("#live-start").disabled = true;
  $("#live-flag").textContent = `LIVE · run ${started.id}`;
  $("#live-flag").classList.add("is-on");
  pollLive();
}
async function pollLive() {
  const R = S.race;
  if (!R.live) return;
  try {
    const run = await api(`/api/runs/${R.id}`);
    R.run = run;
    if (run.current_game !== R.liveGame) { R.liveGame = run.current_game; R.liveStart = Date.now(); }
    renderGame(run, run.current_game, Infinity, true);
    const playing = Object.values(run.games[run.current_game].trials).some((t) => t.status === "playing");
    $("#race-clock").textContent = fmtClock(playing ? Date.now() - R.liveStart : gameEnd(run, run.current_game));
    if (run.status === "running") {
      setRaceState(playing ? "RACING" : "NEXT PUZZLE", "is-running");
      R.poll = setTimeout(pollLive, 600);
      return;
    }
    setRaceState(run.status === "completed" ? "RACE COMPLETE" : `ABORTED: ${run.abort_reason}`, "is-done");
  } catch (e) {
    setRaceState(`ERROR: ${e.message}`, "is-done");
  }
  R.live = false;
  $("#live-abort").disabled = true;
  $("#live-start").disabled = !S.config.live_ready;
  $("#live-flag").classList.remove("is-on");
  await refreshRuns();
}

/* ------------------------------------------------------------------ dashboard */
function bars(title, rows, key, { digits = 0, suffix = "", lowerBetter = false } = {}) {
  const vals = rows.map((r) => r[key]).filter((v) => v != null);
  const max = Math.max(...vals, 1e-9);
  return `<div class="panel"><h3>${title}</h3><div class="bars">${rows.map((r) => {
    const m = S.config.models.find((x) => x.key === r.model);
    const v = r[key];
    const pct = v == null ? 0 : Math.max(2, (v / max) * 100);
    return `<div class="bar__row"><span class="bar__label">${esc(m ? m.name : r.model)}</span>
      <span class="bar__track"><span class="bar__fill ${m && m.api === "chat" ? "bar__fill--llm" : "bar__fill--dec"}" style="width:${pct}%;display:block"></span></span>
      <span class="bar__val">${na(v, digits, suffix)}</span></div>`;
  }).join("")}</div>${lowerBetter ? `<div class="meta-line">lower is better</div>` : ""}</div>`;
}

async function renderDashboard() {
  const id = $("#dash-run").value;
  if (!id) { $("#dash-body").innerHTML = `<div class="empty">No runs yet. Start one from the Race tab.</div>`; return; }
  const [st, run] = await Promise.all([api(`/api/runs/${id}/stats`), api(`/api/runs/${id}`)]);
  const ms = st.models;
  $("#dash-hint").textContent =
    `${st.tier} · ${st.games} puzzles · ${st.status} · reported spend $${st.spend.reported_cost_usd.toFixed(4)}`;
  const name = (k) => S.config.models.find((m) => m.key === k).name;

  const table = `<div class="panel"><h3>Benchmark statistics</h3><div class="tbl-wrap"><table class="tbl">
    <thead><tr><th>Model</th><th>Avg latency / move</th><th>Avg time / puzzle</th><th>Total time</th>
      <th>Avg moves</th><th>Total moves</th><th>Success rate</th><th>Avg optimality gap</th>
      <th>Optimal-move rate</th><th>Malformed</th><th>Errors</th><th>Retries</th><th>Cost</th></tr></thead>
    <tbody>${ms.map((m) => `<tr>
      <td>${esc(name(m.model))}</td><td>${na(m.avg_latency_ms, 0, " ms")}</td>
      <td>${na(m.avg_trial_time_s, 1, " s")}</td><td>${na(m.total_time_s, 1, " s")}</td>
      <td>${na(m.avg_moves)}</td><td>${m.total_moves}</td>
      <td>${na(m.success_rate_pct, 1, "%")} <span style="color:var(--ink-3)">(${m.solved}/${m.trials})</span></td>
      <td>${m.avg_optimality_gap == null ? "N/A" : `+${m.avg_optimality_gap.toFixed(2)} (n=${m.gap_n})`}</td>
      <td>${na(m.optimal_move_rate_pct, 1, "%")}</td><td>${m.malformed}</td><td>${m.errors}</td>
      <td>${m.retries}</td><td>$${m.cost_usd.toFixed(4)}</td></tr>`).join("")}
      <tr class="is-ref"><td>Random moves (baseline)</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td>
      <td>${na(st.random_baseline.success_rate_pct, 2, "%")}</td><td>—</td>
      <td>${na(st.random_baseline.optimal_move_rate_pct_first_turn, 1, "%")}*</td><td>—</td><td>—</td><td>—</td><td>$0</td></tr>
    </tbody></table></div>
    <div class="meta-line">Gap = moves used − exact shortest, solved trials only (unsolved = N/A). Every turn counts as a move,
      including malformed replies and failed requests. *random: share of optimal moves from each puzzle's start state.
      Aborted trials excluded: ${ms.map((m) => m.aborted_trials).reduce((a, b) => a + b, 0)}.</div></div>`;

  const matrix = `<div class="panel" style="margin-top:14px"><h3>Per-puzzle results</h3><div class="tbl-wrap"><table class="tbl">
    <thead><tr><th>Puzzle</th><th>Shortest</th>${S.config.models.map((m) => `<th>${esc(m.name)}</th>`).join("")}</tr></thead>
    <tbody>${run.games.map((g) => `<tr><td>${esc(g.puzzle.id)}${g.repeat ? ` r${g.repeat + 1}` : ""}</td>
      <td>${g.puzzle.shortest_distance ?? "—"}</td>${S.config.models.map((m) => {
        const t = g.trials[m.key];
        if (t.status === "solved") {
          const gap = g.puzzle.shortest_distance != null ? ` (gap +${t.turns - g.puzzle.shortest_distance})` : "";
          return `<td class="cell-ok">✓ ${t.turns}${gap}</td>`;
        }
        if (t.status === "out_of_moves") return `<td class="cell-no">✕ limit</td>`;
        return `<td>${esc(t.status)}</td>`;
      }).join("")}</tr>`).join("")}</tbody></table></div></div>`;

  $("#dash-body").innerHTML = `<div class="dash-grid">
      ${bars("Avg latency per move (ms)", ms, "avg_latency_ms", { lowerBetter: true })}
      ${bars("Success rate (%)", ms, "success_rate_pct", { digits: 1, suffix: "%" })}
      ${bars("Avg moves per puzzle", ms, "avg_moves", { digits: 1, lowerBetter: true })}
    </div>${table}${matrix}`;
}

/* ------------------------------------------------------------------ slide */
async function renderSlide() {
  const id = $("#slide-run").value;
  const el = $("#slide");
  const who = `<div class="slide__who">${esc(S.config.student.name)}<span>${esc(S.config.student.roll)}</span></div>`;
  if (!id) { el.innerHTML = `<div class="slide__top"><div class="slide__title">No results yet</div>${who}</div>`; return; }
  const st = await api(`/api/runs/${id}/stats`);
  const best = (key, low) => {
    const v = st.models.filter((m) => m[key] != null);
    if (!v.length) return null;
    return v.reduce((a, b) => ((low ? b[key] < a[key] : b[key] > a[key]) ? b : a)).model;
  };
  const top = best("success_rate_pct", false);
  const metric = (k, v, sub = "") => `<div><div class="smetric__k">${k}</div><div class="smetric__v">${v}${sub ? ` <small>${sub}</small>` : ""}</div></div>`;
  el.innerHTML = `
    <div class="slide__top">
      <div>
        <div class="slide__kicker">Statistical benchmark · ${esc(st.tier)} tier</div>
        <div class="slide__title">Rubik's Cube Race: results</div>
        <div class="slide__sub">${st.games} puzzles × 4 models · same scrambles · ${st.rules.max_moves}-move limit · HTM</div>
      </div>${who}
    </div>
    <div class="slide__cols">${st.models.map((m) => {
      const info = S.config.models.find((x) => x.key === m.model);
      return `<div class="scol ${m.model === top ? "scol--best" : ""}">
        <div><div class="scol__name">${esc(info.name)}</div><div class="scol__cat">${esc(info.category)}</div></div>
        ${metric("Avg latency / move", na(m.avg_latency_ms, 0), "ms")}
        ${metric("Total solve time", na(m.total_time_s, 1), `s · avg ${na(m.avg_trial_time_s, 1)} s/puzzle`)}
        ${metric("Total moves", m.total_moves, `avg ${na(m.avg_moves)}`)}
        ${metric("Success rate", na(m.success_rate_pct, 0, "%"), `${m.solved}/${m.trials}`)}
        ${metric("Optimality gap", m.avg_optimality_gap == null ? "N/A" : `+${m.avg_optimality_gap.toFixed(2)}`,
                 m.gap_n ? `${m.optimal_solves}/${m.gap_n} optimal` : "no solves")}
        ${metric("Optimal-move rate", na(m.optimal_move_rate_pct, 0, "%"), "of turns")}
        ${metric("Invalid replies", m.malformed + m.errors, `${m.malformed} malformed · ${m.errors} errors`)}
      </div>`;
    }).join("")}</div>
    <div class="slide__foot">
      <span>Random-move baseline solve rate: ${na(st.random_baseline.success_rate_pct, 2, "%")}</span>
      <span>Reported API spend: $${st.spend.reported_cost_usd.toFixed(4)}</span>
      <span>run ${esc(st.run_id)}</span>
    </div>`;
}

/* ------------------------------------------------------------------ wiring */
function showView(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("is-active", b.dataset.view === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("is-active", v.id === `view-${name}`));
  if (name === "dashboard") renderDashboard().catch((e) => ($("#dash-body").innerHTML = `<div class="empty">${esc(e.message)}</div>`));
  if (name === "slide") renderSlide().catch((e) => ($("#slide").textContent = e.message));
}

async function init() {
  S.config = await api("/api/config");
  $("#student-name").textContent = S.config.student.name;
  $("#student-roll").textContent = S.config.student.roll;
  $("#live-tier").innerHTML = Object.entries(S.config.tiers).map(([t, v]) =>
    `<option value="${t}" ${t === "primary" ? "selected" : ""}>${t} (${v.lengths[0]}–${v.lengths[1]} moves, ${v.count} puzzles)</option>`).join("");
  const syncCount = () => { $("#live-puzzles").value = S.config.tiers[$("#live-tier").value].count;
                            $("#live-puzzles").max = S.config.tiers[$("#live-tier").value].count; };
  syncCount();
  $("#live-tier").addEventListener("change", syncCount);
  $("#live-start").disabled = !S.config.live_ready;
  if (!S.config.live_ready) $("#live-flag").textContent = "OPENROUTER_API_KEY not set in .env";
  buildCards();
  await refreshRuns();

  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  $("#source").addEventListener("change", (e) => {
    const live = e.target.value === "live";
    $("#live-controls").classList.toggle("is-hidden", !live);
    $("#replay-controls").classList.toggle("is-hidden", live);
  });
  $("#replay-run").addEventListener("change", fillStartPuzzles);
  $("#replay-play").addEventListener("click", () => startReplay().catch((e) => alert(e.message)));
  $("#replay-stop").addEventListener("click", () => { stopReplay(); setRaceState("PAUSED"); });
  $("#replay-speed").addEventListener("change", (e) => (S.race.speed = Number(e.target.value)));
  $("#live-start").addEventListener("click", startLive);
  $("#live-abort").addEventListener("click", async () => {
    if (S.race.id) await api(`/api/runs/${S.race.id}/abort`, { method: "POST" }).catch(() => {});
  });
  $("#dash-run").addEventListener("change", renderDashboard);
  $("#slide-run").addEventListener("change", renderSlide);
  $("#slide-full").addEventListener("click", () => $("#slide").requestFullscreen?.());

  if (S.config.active_run) {               // page reloaded during a live run
    $("#source").value = "live";
    $("#source").dispatchEvent(new Event("change"));
    Object.assign(S.race, { live: true, id: S.config.active_run, liveGame: -1 });
    $("#live-abort").disabled = false; $("#live-start").disabled = true;
    pollLive();
  }
}

init().catch((e) => { document.body.insertAdjacentHTML("beforeend", `<div class="empty">Failed to load: ${esc(e.message)}</div>`); });
