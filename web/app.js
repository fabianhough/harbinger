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

  const KIND_WORDS = { clear: "Clear", cloudy: "Cloudy", fog: "Fog", rain: "Rain", snow: "Snow", storm: "Storms" };
  const INCLEMENT = new Set(["rain", "snow", "storm"]);

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

  const hourLabel = (d) => fmtHour.format(d).toLowerCase().replace(" ", "");

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
    const [hm, ampm] = fmtClock.format(d).split(" ");
    const w = state?.slots?.weather;

    const chips = w
      ? verdictChip("Rain", w.verdicts.umbrella) + verdictChip("Jacket", w.verdicts.jacket)
      : "";

    const status = lastFetchOk === false
      ? `state unreachable · last ${state ? ago(state.generated_at) : "never"}`
      : state ? `updated ${ago(state.generated_at)}` : "loading";

    $("band").innerHTML = `
      <div class="clock"><span class="clock-time num">${esc(hm)}</span><span class="clock-ampm">${esc(ampm ?? "")}</span></div>
      <div class="date">${esc(fmtDate.format(d))}</div>
      <div class="verdicts">${chips}</div>
      <div class="band-status">${esc(status)}</div>`;
  }

  function verdictChip(label, v) {
    return `
      <div class="verdict">
        <span class="label">${esc(label)}</span>
        <span class="verdict-value">${esc(v.answer)}</span>
        <span class="verdict-detail">${esc(v.detail)}</span>
      </div>`;
  }

  // ---------- weather strip ----------

  function renderStrip(w) {
    if (!w) return missingPane("weather", "Weather");
    const hours = w.hourly.slice(0, C.hourlyHours);
    const n = hours.length;

    const temps = hours.map((h) => h.temp_f);
    const tMin = Math.min(...temps) - 2, tMax = Math.max(...temps) + 2;
    const yOf = (t) => (100 - ((t - tMin) / (tMax - tMin)) * 100).toFixed(2);
    const pts = hours.map((h, i) => `${i + 0.5},${yOf(h.temp_f)}`).join(" ");

    const cells = hours.map((h, i) => {
      const col = `grid-column:${i + 1}`;
      const t = new Date(h.t);
      const kind = KIND_WORDS[h.kind] ?? h.kind;
      return `
        ${INCLEMENT.has(h.kind) ? `<div class="h-shade" style="${col}"></div>` : ""}
        <div class="h-time ${i === 0 ? "now" : ""}" style="${col}">${i === 0 ? "Now" : esc(hourLabel(t))}</div>
        <div class="h-kind ${esc(h.kind)}" style="${col}">${esc(kind)}</div>
        <div class="h-temp num" style="${col}">${Math.round(h.temp_f)}°</div>
        <div class="h-pop" style="${col}">
          ${h.pop >= 10 ? `<span class="h-pop-n num">${h.pop}%</span>` : ""}
          <div class="h-pop-bar" style="height:${h.pop}%"></div>
        </div>`;
    }).join("");

    const first = new Date(hours[0].t), last = new Date(hours[n - 1].t);
    const alerts = (w.alerts ?? []).map((a) => {
      let s = 0, e = n - 1;
      if (a.onset) s = Math.max(0, hours.findIndex((h) => new Date(h.t) >= new Date(a.onset)));
      if (a.ends) {
        const idx = hours.findIndex((h) => new Date(h.t) >= new Date(a.ends));
        e = idx === -1 ? n - 1 : Math.max(s, idx - 1);
      }
      if ((a.ends && new Date(a.ends) <= first) || (a.onset && new Date(a.onset) > last)) return "";
      return `<div class="h-alert ${esc(a.severity)}" style="grid-column:${s + 1} / ${e + 2}">${esc(a.headline)}</div>`;
    }).join("");

    const line = `
      <div class="h-line-area">
        <svg class="h-line" viewBox="0 0 ${n} 100" preserveAspectRatio="none" aria-hidden="true">
          <polygon class="temp-area" points="0.5,100 ${pts} ${n - 0.5},100"/>
          <polyline class="temp-line" points="${pts}" vector-effect="non-scaling-stroke"/>
        </svg>
      </div>`;

    const body = `
      <div class="strip-body">
        <div class="wx-anchor">
          <span class="wx-temp num">${Math.round(w.now.temp_f)}°</span>
          <span class="wx-cond">${esc(w.now.short)}</span>
          <span class="wx-sub">feels ${Math.round(w.now.feels_f)}°${w.now.wind ? ` · ${esc(w.now.wind)}` : ""}</span>
          <span class="wx-range num"><strong>${Math.round(w.today.high_f)}°</strong> / ${Math.round(w.today.low_f)}°</span>
        </div>
        <div class="hours" style="--hours:${n}" role="img" aria-label="Hourly forecast for the next ${n} hours">
          ${cells}${alerts}${line}
        </div>
      </div>`;
    return paneShell("weather", "Weather", body, w.updated_at);
  }

  // ---------- transit ----------

  function renderTransit(t) {
    if (!t) return missingPane("transit", "Trains");
    const major = C.emphasizedDirection;
    const minor = major === "N" ? "S" : "N";
    const header = (dir) => t.directions?.[dir] ?? t.lines[0]?.directions[dir]?.label ?? "";
    const head = `
      <div class="board-head">
        <span></span>
        <span class="label">To ${esc(header(major))}</span>
        <span class="label">To ${esc(header(minor))}</span>
      </div>`;
    const lines = t.lines.map((l) => {
      const alerts = (l.alerts ?? []).map((a) => `
        <div class="line-alert">
          <span class="chip ${a.scope === "station" ? "station" : ""}">${esc(a.scope === "station" ? "this station" : a.type)}</span>
          <span>${bracketsToBullets(a.header)}</span>
        </div>`).join("");
      return `
        <div class="line">
          ${bullet(l.route, "lg")}
          ${dirBlock(l.directions[major], "major", header(major))}
          ${dirBlock(l.directions[minor], "minor", header(minor))}
          ${alerts ? `<div class="line-alerts">${alerts}</div>` : ""}
        </div>`;
    }).join("");
    return paneShell("transit", t.station.name, head + `<div class="lines">${lines}</div>`, t.updated_at);
  }

  function dirBlock(d, kind, header) {
    // Trains arriving sooner than the walk to the station are not reachable.
    const reachable = (d?.arrivals_min ?? []).filter((m) => m >= C.walkMinutes).slice(0, 3);
    const nums = reachable.length
      ? `<span class="first num">${Math.round(reachable[0])}</span>` +
        reachable.slice(1).map((m) => `<span class="sep">·</span><span class="rest num">${Math.round(m)}</span>`).join("") +
        `<span class="unit">min</span>`
      : `<span class="none">none in reach</span>`;
    // A line whose terminal differs from the column header names it beneath the number.
    const dest = d?.label && d.label !== header ? `<span class="dest">${esc(d.label)}</span>` : "";
    return `
      <div class="dir ${kind}">
        <div class="arrivals">${nums}</div>
        ${dest}
      </div>`;
  }

  // ---------- bikes ----------

  function renderBikes(b) {
    if (!b) return missingPane("bikes", "Citi Bike");
    const stations = b.stations.map((s) => {
      const origin = s.role === "origin";
      const counts = origin
        ? `${count("e-bike", s.ebike)}${count("classic", s.classic)}${count("docks", s.docks, "minor")}`
        : `${count("docks", s.docks)}${count("e-bike", s.ebike, "minor")}${count("classic", s.classic, "minor")}`;
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

  // ---------- agent column ----------

  function renderHeadline(n) {
    if (!n?.headline) return "";
    return `
      <section class="pane pane-headline ${freshness("notices", n.updated_at)}">
        <span class="label">Headline</span>
        <p class="headline-text">${esc(n.headline)}</p>
      </section>`;
  }

  function renderNotices(n) {
    if (!n) return missingPane("notices", "Notices");
    return paneShell("notices", "Notices", `<div class="notices-text">${noticesHtml(n.text)}</div>`, n.updated_at, n.priority === "high" ? "high" : "");
  }

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

  // Nothing on the board is allowed to clip mid-line: notices clamps to whole lines.
  function fitText() {
    document.querySelectorAll(".notices-text").forEach((el) => {
      const lineHeight = parseFloat(getComputedStyle(el).lineHeight);
      const lines = Math.max(1, Math.floor(el.clientHeight / lineHeight));
      if (el.scrollHeight > el.clientHeight) {
        el.style.display = "-webkit-box";
        el.style.webkitBoxOrient = "vertical";
        el.style.webkitLineClamp = String(lines);
      }
    });
  }

  // News that does not fit scrolls: pause at the top, step one item at a time,
  // pause at the bottom, return to the top. The list is re-queried on every step
  // because the pane is re-rendered on each poll.
  const newsScroll = { index: 0, timer: null };
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function scheduleNewsScroll(reset) {
    clearTimeout(newsScroll.timer);
    if (reset) newsScroll.index = 0;
    const list = document.querySelector(".news-list");
    if (!list || list.scrollHeight <= list.clientHeight + 1) return;
    const atEnd = list.scrollTop + list.clientHeight >= list.scrollHeight - 1;
    const delay = newsScroll.index === 0 || atEnd ? C.newsScroll.pauseMs : C.newsScroll.stepMs;
    newsScroll.timer = setTimeout(() => {
      const l = document.querySelector(".news-list");
      if (!l) return;
      const items = [...l.children];
      if (l.scrollTop + l.clientHeight >= l.scrollHeight - 1 || newsScroll.index >= items.length - 1) {
        newsScroll.index = 0;
        l.scrollTo({ top: 0, behavior: "auto" });
      } else {
        newsScroll.index += 1;
        l.scrollTo({ top: items[newsScroll.index].offsetTop, behavior: reducedMotion ? "auto" : "smooth" });
      }
      scheduleNewsScroll(false);
    }, delay);
  }

  // ---------- orchestration ----------

  let lastNewsJson = null;

  function applyLayout() {
    const root = document.documentElement.style;
    root.setProperty("--cols", C.layout.columns);
    root.setProperty("--band-h", C.layout.bandHeight);
    root.setProperty("--strip-h", C.layout.stripHeight);
    root.setProperty("--left-bottom", C.layout.leftBottom);
  }

  function render() {
    renderBand();
    const s = state?.slots ?? {};
    $("strip").innerHTML = renderStrip(s.weather);
    $("bottom").innerHTML = renderTransit(s.transit) + renderBikes(s.bikes);
    const headline = renderHeadline(s.notices);
    const told = $("told");
    told.classList.toggle("no-headline", !headline);
    // Re-rendering must not reset a scrolling news list unless the news changed.
    const newsJson = JSON.stringify(s.news?.items ?? null);
    const newsChanged = newsJson !== lastNewsJson;
    lastNewsJson = newsJson;
    const prevTop = document.querySelector(".news-list")?.scrollTop ?? 0;
    told.innerHTML = headline + renderNotices(s.notices) + renderNews(s.news);
    if (!newsChanged) {
      const list = document.querySelector(".news-list");
      if (list) list.scrollTop = prevTop;
    }
    fitText();
    scheduleNewsScroll(newsChanged);
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
