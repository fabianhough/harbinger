# docs/

Provenance for everything Harbinger depends on that it does not control.

## Layout

- `sources/` — one file per external data source.
- `recon/` — the exact scripts used to produce the findings in `sources/`, committed
  so every "How" section is reproducible from a clean shell.

## Template for `sources/<name>.md`

Each source file has these sections, in this order:

1. **Where** — endpoint URLs, official documentation links, auth and rate-limit terms.
2. **How** — the exact commands or script used, and the date they were run.
3. **What** — payload structure, the fields Harbinger cares about, a trimmed sample,
   and freshness semantics (timestamps, cache headers, update cadence).
4. **Caveats** — failure modes, staleness behaviour, gaps and surprises.

## Rules

- Every entry is dated. A finding without a date is a rumour.
- Worked examples use **placeholder locations only**: Jay St-MetroTech for the subway,
  a Times Square coordinate for weather and bikes. Real station IDs, coordinates and
  addresses never appear in this repository. They live in gitignored config.
- Samples are trimmed and redacted. No raw full-feed dumps.
- A source is documented here **before** it is wired into code.
