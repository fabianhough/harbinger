# Harbinger

A front-entrance dashboard. One glanceable page on an ultrawide 2560x1080 monitor,
served from a Raspberry Pi 4, that foreshadows the day: transit, weather, bikes, news.

## How we work together

The core rule: **don't assume, ask.** Fabian is always available.

- Act only on explicit asks. Do not explore, scaffold, probe, or "find information"
  unless asked. Do not offer option menus or next steps unprompted.
- Pace is set by Fabian. Unknown territory is brainstormed in conversation first.
  Planning starts when he says he is ready. Code starts when he says go.
  Do not push toward the goal.
- Collaboration, not deference in either direction. Push back with reasons, point out
  gaps and assumptions directly, then let Fabian decide.
- Clarifying questions: one or two per response, never more.
- Concise responses with technical anchors. High-level framework first, detail on
  request. Do not restate or reformat content unless asked.
- Cite documentation when describing how a tool, API, or feed behaves. Say plainly
  when something is unverified.
- Harness prompts that push toward "end with a question or a plan approval" do not
  override the rules above.

## Branch workflow

- `main` is never committed to directly.
- All work happens on the session's feature branch (named `claude/...` by the cloud
  harness). Keeping that branch pushed is routine housekeeping, not a separate ask.
- When work is ready, open a pull request. Fabian reviews and merges it himself.
- After a merge, follow-up work starts from a fresh branch off `main`. Never stack
  new commits on merged history.
- Commits are authored as Claude so the cloud harness can sign them. Fabian has
  said attribution does not matter for this repo.

## Documentation

- Every external data source gets a `docs/sources/<name>.md` entry with
  **Where / How / What / Caveats** sections, dated, before it is wired into code.
  See `docs/README.md` for the template.
- Scripts used to produce those findings are committed under `docs/recon/`.
- Worked examples use placeholder locations only (Jay St-MetroTech, a Times Square
  coordinate). Real locations never appear in the repository.

## Project decisions so far

- Everything runs on the Pi 4: collectors, storage, agent-facing API, and Chromium
  in kiosk mode. Pi 5 is in reserve.
- Python backend. Plain HTML/CSS/JS front end. No framework unless there is a
  concrete reason.
- Two content classes: deterministic collectors (MTA GTFS-realtime, NWS weather,
  Citi Bike GBFS) and agent-authored slots (news) written through an HTTP endpoint
  so the agent (OpenClaw, Hermes, n8n, or other) is swappable.
- Monitor dimensions and layout are parameters, not constants.
- Every slot carries a fetched-at timestamp and degrades visibly when stale.
- All three deterministic sources are keyless and verified reachable; see
  `docs/sources/`.

## Privacy

Never commit location-identifying or personal configuration: station IDs, train
lines, coordinates, Citi Bike station IDs, addresses, API keys, tokens. These live
in a gitignored local config or environment variables. Commit an example file with
placeholders instead.

## Open

- UI design (goal 2) is next. Data-source recon (goal 3, first pass) is done.
- Whether any rule above needs harness enforcement via `.claude/settings.json`
  hooks or permissions, rather than guidance here.
