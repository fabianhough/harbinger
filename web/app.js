(() => {
  "use strict";

  const C = window.HARBINGER_CONFIG;

  // Official MTA line colours, keyed by GTFS route_id.
  const ROUTE_COLORS = {
    A: "#0039A6", C: "#0039A6", E: "#0039A6",
    B: "#FF6319", D: "#FF6319", F: "#FF6319", FX: "#FF6319", M: "#FF6319",
    G: "#6CBE45",
    J: "#996633", Z: "#996633",
    L: "#A7A9AC",
    N: "#FCCC0A", Q: "#FCCC0A", R: "#FCCC0A", W: "#FCCC0A",
    S: "#808183", GS: "#808183", FS: "#808183", H: "#808183",
    1: "#EE352E", 2: "#EE352E", 3: "#EE352E",
    4: "#00933C", 5: "#00933C", 6: "#00933C", "6X": "#00933C",
    7: "#B933AD", "7X": "#B933AD",
    SI: "#0039A6",
  };
  const DARK_TEXT_ROUTES = new Set(["N", "Q", "R", "W"]);
  const ROUTE_LABELS = { GS: "S", FS: "S", H: "S", SI: "SIR" };

  let state = null;
  let frozenNow = null;
  let lastFetchOk = null;
  let lastReloadDay = null;

  // ---------- helpers ----------

  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function now() {
    return C.clock === "frozen" && frozenNow ? frozenNow : new Date();
  }

  const fmt = (opts) => new Intl.DateTimeFormat(C.locale, { timeZone: C.timeZone, ...opts });
  const fmtClock = fmt({ hour: "numeric", minute: "2-digit" });
  const fmtDate = fmt({ weekday: "long", month: "long", day: "numeric" });
  const fmtHour = fmt({ hour: "numeric" });

  function ago(iso) {
    const s = (now() - new Date(iso)) / 1000;
    if (s < 45) return "just now";
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    if (s < 86400) return `${Math.round(s / 3600)}h ago`;
    return `${Math.round(s / 86400)}d ago`;
  }

  function freshness(slot, updatedAt) {
    const budget = C.freshnessSeconds[slot] ?? 3600;
    const age = (now() - new Date(updatedAt)) / 1000;
    if (age > budget * 3) return "dead";
    if (age > budget) return "stale";
    return "fresh";
  }

  function bullet(route, size) {
    const bg = ROUTE_COLORS[route] || "#808183";
    const dark = DARK_TEXT_ROUTES.has(route) ? " bullet-dark" : "";
    const label = ROUTE_LABELS[route] || route;
    return `<span class="bullet bullet-${size}${dark}" style="background:${bg}">${esc(label)}</span>`;
  }

  // MTA alert text uses [F] for route bullets.
  const bracketsToBullets = (text) =>
    esc(text).replace(/\[([A-Z0-9]{1,2})\]/g, (_, r) => bullet(r, "xs"));

  // Notices: plain text, newlines kept, **bold** is the only markup.
  const noticesHtml = (text) =>
    esc(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  const minutesLabel = (m) => (m < 1 ? "now" : String(Math.round(m)));

  function paneShell(slot, title, body, updatedAt, extraClass = "") {
    const f = freshness(slot, updatedAt);
    const agePrefix = f === "fresh" ? "" : `${f} · `;
    return `
      <section class="pane pane-${slot} ${f} ${extraClass}" data-slot="${slot}">
        <header class="pane-head"><h2>${esc(title)}</h2><span class="age">${agePrefix}${ago(updatedAt)}</span></header>
        <div class="pane-body">${body}</div>
      </section>`;
  }

  function missingPane(slot, title) {
    return `
      <section class="pane pane-${slot} dead" data-slot="${slot}">
        <header class="pane-head"><h2>${esc(title)}</h2><span class="age">no data</span></header>
        <div class="pane-body empty">Waiting for ${esc(slot)}</div>
      </section>`;
  }

  // ---------- band ----------

  function renderBand() {
    const d = now();
    const timeStr = fmtClock.format(d);
    const [hm, ampm] = timeStr.split(" ");
    const s = state?.slots ?? {};

    const chips = [];
    if (s.weather) {
      const v = s.weather.verdicts;
      chips.push(verdictChip("Umbrella", esc(v.umbrella.answer), v.umbrella.detail));
      chips.push(verdictChip("Jacket", esc(v.jacket.answer), v.jacket.detail));
    }
    if (s.transit) {
      const dir = C.emphasizedDirection;
      const parts = s.transit.lines.map((l) => {
        const a = l.directions[dir]?.arrivals_min ?? [];
        return `${bullet(l.route, "sm")}<span class="num">${a.length ? minutesLabel(a[0]) : "–"}</span>`;
      });
      const label = s.transit.lines[0]?.directions[dir]?.label ?? "Next";
      chips.push(verdictChip(`Next to ${label}`, parts.join(""), `minutes · ${s.transit.station.name}`));
    }
    if (s.bikes) {
      const origins = s.bikes.stations.filter((st) => st.role === "origin");
      const classic = origins.reduce((n, st) => n + st.classic, 0);
      const ebike = origins.reduce((n, st) => n + st.ebike, 0);
      chips.push(verdictChip("Bikes nearby", `<span class="num">${classic + ebike}</span>`, `${classic} classic · ${ebike} electric`));
    }

    const status = lastFetchOk === false
      ? `state unreachable · last ${state ? ago(state.generated_at) : "never"}`
      : state ? `updated ${ago(state.generated_at)}` : "loading";

    $("band").innerHTML = `
      <div class="clock"><span class="clock-time num">${esc(hm)}</span><span class="clock-ampm">${esc(ampm ?? "")}</span></div>
      <div class="date">${esc(fmtDate.format(d))}</div>
      <div class="verdicts">${chips.join("")}</div>
      <div class="band-status">${esc(status)}</div>`;
  }

  function verdictChip(label, valueHtml, detail) {
    return `
      <div class="verdict">
        <span class="label">${esc(label)}</span>
        <span class="verdict-value">${valueHtml}</span>
        <span class="verdict-detail">${esc(detail)}</span>
      </div>`;
  }

  // ---------- weather ----------

  function renderWeather(w) {
    if (!w) return missingPane("weather", "Weather");
    const alerts = (w.alerts ?? [])
      .map((a) => `<div class="wx-alert ${esc(a.severity)}">${esc(a.headline)}</div>`)
      .join("");
    const body = `
      <div class="wx-now">
        <span class="wx-temp num">${Math.round(w.now.temp_f)}°</span>
        <div class="wx-cond">
          <strong>${esc(w.now.short)}</strong>
          <span>feels ${Math.round(w.now.feels_f)}°${w.now.wind ? ` · ${esc(w.now.wind)}` : ""}</span>
        </div>
      </div>
      ${alerts}
      ${hourlyChart(w.hourly)}
      <p class="wx-today"><strong>${Math.round(w.today.high_f)}° / ${Math.round(w.today.low_f)}°</strong> · ${esc(w.today.narrative)}</p>`;
    return paneShell("weather", "Weather", body, w.updated_at);
  }

  // Two small rows on one time axis: temperature (line) and chance of rain (bars).
  // Each row has its own scale; they share only the x positions.
  function hourlyChart(hourly) {
    const n = hourly.length;
    if (n < 2) return "";
    const W = 1000, H = 560;
    const padL = 24, padR = 48;
    const tTop = 60, tBot = 300;
    const rTop = 380, rBot = 470;
    const labelY = 530;
    const x = (i) => padL + (i * (W - padL - padR)) / (n - 1);

    const temps = hourly.map((h) => h.temp_f);
    const tMin = Math.min(...temps) - 3, tMax = Math.max(...temps) + 3;
    const y = (t) => tBot - ((t - tMin) / (tMax - tMin)) * (tBot - tTop);

    const pts = hourly.map((h, i) => `${x(i).toFixed(1)},${y(h.temp_f).toFixed(1)}`);
    const line = `<polyline class="temp-line" points="${pts.join(" ")}" vector-effect="non-scaling-stroke"/>`;
    const area = `<polygon class="temp-area" points="${x(0).toFixed(1)},${tBot} ${pts.join(" ")} ${x(n - 1).toFixed(1)},${tBot}"/>`;

    // Selective labels: first, last, and the extremes if they are elsewhere.
    const iMax = temps.indexOf(Math.max(...temps));
    const iMin = temps.indexOf(Math.min(...temps));
    const labelIdx = new Set([0, n - 1, iMax, iMin]);
    const tLabels = [...labelIdx].map((i) => {
      const anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
      return `<text class="t-label" x="${x(i).toFixed(1)}" y="${(y(temps[i]) - 18).toFixed(1)}" text-anchor="${anchor}">${Math.round(temps[i])}°</text>
              <circle class="temp-dot" cx="${x(i).toFixed(1)}" cy="${y(temps[i]).toFixed(1)}" r="7"/>`;
    }).join("");

    const barW = Math.max(8, ((W - padL - padR) / (n - 1)) * 0.5);
    const bars = hourly.map((h, i) => {
      const hgt = Math.max(2, ((rBot - rTop) * h.pop) / 100);
      const bx = x(i) - barW / 2;
      const lbl = h.pop >= 10 ? `<text class="rain-label" x="${x(i).toFixed(1)}" y="${(rBot - hgt - 10).toFixed(1)}" text-anchor="middle">${h.pop}%</text>` : "";
      return `<rect class="rain-bar" x="${bx.toFixed(1)}" y="${(rBot - hgt).toFixed(1)}" width="${barW.toFixed(1)}" height="${hgt.toFixed(1)}" rx="4"/>${lbl}`;
    }).join("");

    const hourLabels = hourly.map((h, i) => (i % 3 === 0 || i === n - 1)
      ? `<text x="${x(i).toFixed(1)}" y="${labelY}" text-anchor="${i === n - 1 ? "end" : i === 0 ? "start" : "middle"}">${esc(fmtHour.format(new Date(h.t)).toLowerCase().replace(" ", ""))}</text>`
      : "").join("");

    return `
      <svg class="wx-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Temperature and chance of rain for the next ${n} hours">
        <line class="grid" x1="${padL}" y1="${tBot}" x2="${W - padR}" y2="${tBot}"/>
        ${area}${line}${tLabels}
        <text x="${padL}" y="${rTop - 16}">chance of rain</text>
        <line class="grid" x1="${padL}" y1="${rBot}" x2="${W - padR}" y2="${rBot}"/>
        ${bars}
        ${hourLabels}
      </svg>`;
  }

  // ---------- transit ----------

  function renderTransit(t) {
    if (!t) return missingPane("transit", "Trains");
    const major = C.emphasizedDirection;
    const minor = major === "N" ? "S" : "N";
    const lines = t.lines.map((l) => {
      const alerts = (l.alerts ?? []).map((a) => `
        <div class="line-alert">
          <span class="chip ${a.scope === "station" ? "station" : ""}">${esc(a.scope === "station" ? "this station" : a.type)}</span>
          <span>${bracketsToBullets(a.header)}</span>
        </div>`).join("");
      return `
        <div class="line">
          ${bullet(l.route, "lg")}
          <div class="dirs">
            ${dirBlock(l.directions[major], "major")}
            ${dirBlock(l.directions[minor], "minor")}
          </div>
          ${alerts ? `<div class="line-alerts">${alerts}</div>` : ""}
        </div>`;
    }).join("");
    return paneShell("transit", t.station.name, `<div class="lines">${lines}</div>`, t.updated_at);
  }

  function dirBlock(d, kind) {
    const a = d?.arrivals_min ?? [];
    const label = d?.label ?? "";
    const nums = a.length
      ? `<span class="first num">${minutesLabel(a[0])}</span>` +
        a.slice(1).map((m) => `<span class="rest num">${minutesLabel(m)}</span>`).join("") +
        `<span class="unit">min</span>`
      : `<span class="none">no trains</span>`;
    return `
      <div class="dir ${kind}">
        <span class="label">${esc(label)}</span>
        <div class="arrivals">${nums}</div>
      </div>`;
  }

  // ---------- bikes ----------

  function renderBikes(b) {
    if (!b) return missingPane("bikes", "Citi Bike");
    const stations = b.stations.map((s) => {
      const origin = s.role === "origin";
      const counts = origin
        ? `${count("classic", s.classic)}${count("e-bike", s.ebike)}${count("docks", s.docks, "minor")}`
        : `${count("docks", s.docks)}${count("classic", s.classic, "minor")}${count("e-bike", s.ebike, "minor")}`;
      return `
        <div class="station ${s.renting ? "" : "closed"}">
          <span class="label">${origin ? "from" : "to"}</span>
          <span class="station-name">${esc(s.name)}</span>
          <div class="counts">${counts}</div>
        </div>`;
    }).join("");
    return paneShell("bikes", "Citi Bike", `<div class="stations">${stations}</div>`, b.updated_at);
  }

  function count(label, n, kind = "") {
    return `
      <div class="count ${kind} ${n === 0 ? "zero" : ""}">
        <span class="count-n num">${n}</span>
        <span class="label">${esc(label)}</span>
      </div>`;
  }

  // ---------- news ----------

  function renderNews(nw) {
    if (!nw) return missingPane("news", "News");
    const items = nw.items.map((it) => `
      <article class="news-item ${esc(it.priority ?? "normal")}">
        <span class="news-mark"></span>
        <h3 class="news-title">${esc(it.title)}</h3>
        <p class="news-summary">${esc(it.summary)}</p>
        <span class="news-meta">${esc(it.source)}${it.published_at ? ` · ${ago(it.published_at)}` : ""}</span>
      </article>`).join("");
    return paneShell("news", "News", `<div class="news-list">${items}</div>`, nw.updated_at);
  }

  // ---------- notices ----------

  function renderNotices(n) {
    if (!n) return missingPane("notices", "Notices");
    return paneShell("notices", "Notices", `<div class="notices-text">${noticesHtml(n.text)}</div>`, n.updated_at, n.priority === "high" ? "high" : "");
  }

  // ---------- orchestration ----------

  function applyLayout() {
    const root = document.documentElement.style;
    root.setProperty("--band-h", C.layout.bandHeight);
    root.setProperty("--cols", Object.values(C.layout.columns).join(" "));
  }

  function render() {
    renderBand();
    const s = state?.slots ?? {};
    $("panes").innerHTML = [
      renderWeather(s.weather),
      renderTransit(s.transit),
      renderBikes(s.bikes),
      renderNews(s.news),
      renderNotices(s.notices),
    ].join("");
    $("board").classList.toggle("offline", lastFetchOk === false);
  }

  async function poll() {
    try {
      const r = await fetch(C.stateUrl, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      state = await r.json();
      frozenNow = new Date(state.generated_at);
      lastFetchOk = true;
    } catch (e) {
      lastFetchOk = false;
      console.warn("state fetch failed", e);
    }
    render();
  }

  function maybeReload() {
    if (!C.reloadAt || C.clock !== "live") return;
    const d = new Date();
    const hm = fmt({ hour: "2-digit", minute: "2-digit", hour12: false }).format(d);
    const day = fmt({ day: "numeric" }).format(d);
    if (hm === C.reloadAt && lastReloadDay !== day) {
      lastReloadDay = day;
      location.reload();
    }
  }

  applyLayout();
  poll();
  setInterval(poll, C.pollMs);
  setInterval(() => { if (C.clock === "live") renderBand(); maybeReload(); }, 1000);
})();
