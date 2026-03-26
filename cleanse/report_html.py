"""
Generates a self-contained HTML cleansing report with three tabbed sections:
  1. Raw Input Data   — the original dirty records as a table
  2. Cleansing Steps  — per-record cards showing field-by-field changes
  3. Clean Output     — the final normalised records
"""

import pandas as pd
from pathlib import Path


# ── HTML template helpers ──────────────────────────────────────────────────────

def _esc(val) -> str:
    """HTML-escape a value for safe insertion."""
    s = str(val) if val is not None else ""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


def _dirty_table(raw_records: list) -> str:
    fields = ["name", "npi", "role", "credential_type", "license_number",
              "license_expiry", "state", "specialty", "organization"]
    rows = ""
    for i, rec in enumerate(raw_records):
        cells = "".join(
            f'<td class="null-cell">(missing)</td>'
            if rec.get(f) is None or str(rec.get(f, "")).strip() == ""
            else f'<td>{_esc(rec.get(f, ""))}</td>'
            for f in fields
        )
        rows += f'<tr><td class="idx">#{i}</td>{cells}</tr>\n'

    headers = "".join(f"<th>{h}</th>" for h in ["#"] + fields)
    return f"""
<div class="table-wrap">
  <table class="data-table">
    <thead><tr>{headers}</tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def _clean_table(clean_df: pd.DataFrame) -> str:
    cols = ["name", "npi", "credential_type", "license_number",
            "license_expiry", "state", "specialty", "organization"]
    cols = [c for c in cols if c in clean_df.columns]
    rows = ""
    for i, row in clean_df.iterrows():
        cells = ""
        for c in cols:
            val = row[c]
            if pd.isna(val) or str(val).strip() in ("", "nan", "NaT"):
                cells += '<td class="null-cell">(missing)</td>'
            elif c == "license_expiry":
                try:
                    cells += f'<td>{pd.Timestamp(val).strftime("%Y-%m-%d")}</td>'
                except Exception:
                    cells += f'<td>{_esc(val)}</td>'
            else:
                cells += f'<td>{_esc(val)}</td>'
        rows += f"<tr>{cells}</tr>\n"

    headers = "".join(f"<th>{c}</th>" for c in cols)
    return f"""
<div class="table-wrap">
  <table class="data-table">
    <thead><tr>{headers}</tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""


def _steps_cards(reports: list) -> str:
    cards = ""
    for rep in reports:
        idx    = rep["index"]
        name   = _esc(rep["name"]) if rep["name"] else "<em>(no name)</em>"
        status = rep["status"]
        changes = rep.get("changes", [])

        if status == "duplicate":
            dup_of = rep.get("duplicate_of", "?")
            badge = '<span class="badge badge-dup">DUPLICATE REMOVED</span>'
            extra = f'<p class="dup-note">Same NPI as record #{dup_of} after normalisation.</p>'
            change_html = ""
            if changes:
                change_html = "<p class='also-note'>Would have applied:</p>"
                change_html += _change_rows(changes, muted=True)
            cards += f"""
<div class="record-card card-dup" onclick="this.classList.toggle('open')">
  <div class="card-header">
    <span class="rec-id">#{idx}</span>
    <span class="rec-name">{name}</span>
    {badge}
    <span class="chevron">&#9660;</span>
  </div>
  <div class="card-body">
    {extra}
    {change_html}
  </div>
</div>"""

        elif status == "unchanged":
            badge = '<span class="badge badge-ok">NO CHANGES NEEDED</span>'
            cards += f"""
<div class="record-card card-ok" onclick="this.classList.toggle('open')">
  <div class="card-header">
    <span class="rec-id">#{idx}</span>
    <span class="rec-name">{name}</span>
    {badge}
    <span class="chevron">&#9660;</span>
  </div>
  <div class="card-body"><p>All fields were already in the correct format.</p></div>
</div>"""

        else:
            n = len(changes)
            badge = f'<span class="badge badge-changed">{n} FIELD{"S" if n != 1 else ""} CHANGED</span>'
            cards += f"""
<div class="record-card card-changed open" onclick="this.classList.toggle('open')">
  <div class="card-header">
    <span class="rec-id">#{idx}</span>
    <span class="rec-name">{name}</span>
    {badge}
    <span class="chevron">&#9660;</span>
  </div>
  <div class="card-body">
    {_change_rows(changes)}
  </div>
</div>"""

    return cards


def _change_rows(changes: list, muted: bool = False) -> str:
    cls = "change-row muted" if muted else "change-row"
    rows = ""
    for ch in changes:
        before = _esc(ch["before"])
        after  = _esc(ch["after"])
        rule   = _esc(ch["rule"])
        is_null = ch["after"] in ("None", "NaT")
        after_cls = "after null-val" if is_null else "after"
        rows += f"""
<div class="{cls}">
  <div class="change-field">{_esc(ch['field'])}</div>
  <div class="change-vals">
    <span class="before">{before}</span>
    <span class="arrow">&#8594;</span>
    <span class="{after_cls}">{after}</span>
  </div>
  <div class="change-rule">{rule}</div>
</div>"""
    return rows


def _stats_bar(reports: list, raw_records: list, clean_df: pd.DataFrame) -> str:
    n_raw     = len(raw_records)
    n_clean   = len(clean_df)
    n_dup     = sum(1 for r in reports if r["status"] == "duplicate")
    n_changed = sum(1 for r in reports if r["status"] == "cleaned")
    n_ok      = sum(1 for r in reports if r["status"] == "unchanged")
    n_changes = sum(len(r["changes"]) for r in reports)

    return f"""
<div class="stats-bar">
  <div class="stat"><span class="stat-num">{n_raw}</span><span class="stat-label">Raw Records</span></div>
  <div class="stat-arrow">&#8594;</div>
  <div class="stat highlight-changed"><span class="stat-num">{n_changed}</span><span class="stat-label">Records Changed</span></div>
  <div class="stat highlight-dup"><span class="stat-num">{n_dup}</span><span class="stat-label">Duplicates Removed</span></div>
  <div class="stat highlight-ok"><span class="stat-num">{n_ok}</span><span class="stat-label">Already Clean</span></div>
  <div class="stat-arrow">&#8594;</div>
  <div class="stat highlight-out"><span class="stat-num">{n_clean}</span><span class="stat-label">Clean Records</span></div>
  <div class="stat dim"><span class="stat-num">{n_changes}</span><span class="stat-label">Total Field Fixes</span></div>
</div>"""


# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Segoe UI', Arial, sans-serif;
  background: #0f1117;
  color: #e0e0e0;
  min-height: 100vh;
}

header {
  background: linear-gradient(135deg, #1a237e 0%, #0d47a1 100%);
  padding: 28px 40px 20px;
  border-bottom: 3px solid #2962ff;
}
header h1 { font-size: 1.6rem; font-weight: 700; color: #fff; }
header p  { color: #90caf9; margin-top: 4px; font-size: 0.9rem; }

/* ── Stats bar ── */
.stats-bar {
  display: flex; align-items: center; gap: 16px;
  flex-wrap: wrap; margin-top: 20px;
}
.stat {
  background: rgba(255,255,255,0.08);
  border-radius: 10px;
  padding: 10px 18px;
  text-align: center;
  min-width: 110px;
}
.stat-num   { display: block; font-size: 1.8rem; font-weight: 700; color: #fff; }
.stat-label { display: block; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: #90caf9; margin-top: 2px; }
.stat-arrow { font-size: 1.4rem; color: #546e7a; }
.highlight-changed { border: 1px solid #ffa726; }
.highlight-changed .stat-num { color: #ffa726; }
.highlight-dup { border: 1px solid #ef5350; }
.highlight-dup .stat-num { color: #ef5350; }
.highlight-ok  { border: 1px solid #66bb6a; }
.highlight-ok  .stat-num { color: #66bb6a; }
.highlight-out { border: 1px solid #42a5f5; background: rgba(66,165,245,0.12); }
.highlight-out .stat-num { color: #42a5f5; }
.dim .stat-num { color: #90a4ae; }

/* ── Tab nav ── */
.tab-nav {
  display: flex; gap: 0;
  background: #161b22;
  border-bottom: 2px solid #21262d;
  padding: 0 40px;
  position: sticky; top: 0; z-index: 10;
}
.tab-btn {
  background: none; border: none; cursor: pointer;
  padding: 16px 28px;
  color: #8b949e;
  font-size: 0.92rem; font-weight: 600;
  border-bottom: 3px solid transparent;
  margin-bottom: -2px;
  transition: color 0.2s, border-color 0.2s;
}
.tab-btn:hover { color: #e0e0e0; }
.tab-btn.active { color: #58a6ff; border-bottom-color: #58a6ff; }
.tab-step { display: inline-block; width: 22px; height: 22px; border-radius: 50%;
            background: #30363d; font-size: 0.75rem; line-height: 22px;
            text-align: center; margin-right: 8px; }
.tab-btn.active .tab-step { background: #58a6ff; color: #000; }

/* ── Tab panels ── */
.tab-panel { display: none; padding: 32px 40px; }
.tab-panel.active { display: block; }

.panel-title {
  font-size: 1.1rem; font-weight: 700; color: #c9d1d9;
  margin-bottom: 6px;
}
.panel-sub { color: #8b949e; font-size: 0.85rem; margin-bottom: 20px; }

/* ── Data tables ── */
.table-wrap { overflow-x: auto; border-radius: 10px; border: 1px solid #21262d; }
.data-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.data-table thead tr { background: #161b22; }
.data-table th {
  padding: 10px 14px; text-align: left;
  color: #8b949e; font-weight: 600;
  border-bottom: 1px solid #21262d;
  white-space: nowrap;
}
.data-table td {
  padding: 9px 14px;
  border-bottom: 1px solid #1c2128;
  vertical-align: top;
}
.data-table tbody tr:nth-child(even) { background: #0d1117; }
.data-table tbody tr:hover { background: #1c2128; }
.data-table .idx { color: #8b949e; font-weight: 600; width: 36px; }
.null-cell { color: #6e7681; font-style: italic; }

/* ── Record cards ── */
.record-card {
  border: 1px solid #21262d;
  border-radius: 10px;
  margin-bottom: 10px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.2s;
}
.record-card:hover { border-color: #444c56; }
.card-changed { border-left: 4px solid #ffa726; }
.card-dup     { border-left: 4px solid #ef5350; }
.card-ok      { border-left: 4px solid #66bb6a; }

.card-header {
  display: flex; align-items: center; gap: 12px;
  padding: 13px 18px;
  background: #161b22;
  user-select: none;
}
.rec-id   { font-weight: 700; color: #8b949e; min-width: 36px; }
.rec-name { font-weight: 600; color: #e0e0e0; flex: 1; }
.chevron  { color: #555; font-size: 0.75rem; transition: transform 0.25s; }
.record-card.open .chevron { transform: rotate(180deg); }

.card-body {
  display: none;
  padding: 16px 18px;
  background: #0d1117;
}
.record-card.open .card-body { display: block; }

/* ── Badges ── */
.badge {
  font-size: 0.68rem; font-weight: 700;
  padding: 3px 8px; border-radius: 20px;
  letter-spacing: 0.04em;
  white-space: nowrap;
}
.badge-changed { background: rgba(255,167,38,0.15); color: #ffa726; border: 1px solid rgba(255,167,38,0.4); }
.badge-dup     { background: rgba(239,83,80,0.15);  color: #ef5350; border: 1px solid rgba(239,83,80,0.4); }
.badge-ok      { background: rgba(102,187,106,0.15);color: #66bb6a; border: 1px solid rgba(102,187,106,0.4); }

/* ── Change rows ── */
.change-row {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 6px 12px;
  padding: 10px 0;
  border-bottom: 1px solid #1c2128;
  align-items: start;
}
.change-row:last-child { border-bottom: none; }
.change-row.muted { opacity: 0.55; }

.change-field {
  font-family: 'Courier New', monospace;
  font-size: 0.8rem;
  color: #8b949e;
  padding-top: 2px;
}
.change-vals {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.before {
  background: rgba(239,83,80,0.12);
  border: 1px solid rgba(239,83,80,0.3);
  color: #ef9a9a;
  padding: 2px 8px; border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 0.8rem;
  text-decoration: line-through;
  text-decoration-color: rgba(239,83,80,0.5);
}
.after {
  background: rgba(102,187,106,0.12);
  border: 1px solid rgba(102,187,106,0.3);
  color: #a5d6a7;
  padding: 2px 8px; border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 0.8rem;
}
.null-val {
  background: rgba(144,164,174,0.12);
  border: 1px solid rgba(144,164,174,0.3);
  color: #90a4ae;
}
.arrow { color: #555; font-size: 1rem; }
.change-rule {
  grid-column: 2;
  font-size: 0.75rem; color: #6e7681;
  font-style: italic;
}
.dup-note   { color: #ef9a9a; font-size: 0.85rem; margin-bottom: 8px; }
.also-note  { color: #8b949e; font-size: 0.82rem; margin: 8px 0 4px; }

/* ── Expand / collapse all ── */
.toolbar {
  display: flex; gap: 10px;
  margin-bottom: 18px;
}
.toolbar-btn {
  background: #21262d; border: 1px solid #30363d;
  color: #8b949e; padding: 6px 14px;
  border-radius: 6px; cursor: pointer; font-size: 0.8rem;
}
.toolbar-btn:hover { background: #30363d; color: #e0e0e0; }
"""

# ── JS ────────────────────────────────────────────────────────────────────────

JS = """
function showTab(id) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('panel-' + id).classList.add('active');
  document.getElementById('btn-' + id).classList.add('active');
}

function expandAll() {
  document.querySelectorAll('.record-card').forEach(c => c.classList.add('open'));
}
function collapseAll() {
  document.querySelectorAll('.record-card').forEach(c => c.classList.remove('open'));
}
"""

# ── Main generator ────────────────────────────────────────────────────────────

def generate_cleansing_html(
    raw_records: list,
    reports: list,
    clean_df: pd.DataFrame,
) -> str:
    """Return a complete self-contained HTML cleansing report."""
    stats   = _stats_bar(reports, raw_records, clean_df)
    dirty   = _dirty_table(raw_records)
    steps   = _steps_cards(reports)
    cleaned = _clean_table(clean_df)

    n_raw   = len(raw_records)
    n_clean = len(clean_df)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Healthcare Credentialing - Data Cleansing Report</title>
  <style>{CSS}</style>
</head>
<body>

<header>
  <h1>Healthcare Credentialing Demo &mdash; Data Cleansing Report</h1>
  <p>Healthcare provider credentialing &middot; {n_raw} raw records &rarr; {n_clean} clean records</p>
  {stats}
</header>

<nav class="tab-nav">
  <button id="btn-input"  class="tab-btn active" onclick="showTab('input')">
    <span class="tab-step">1</span>Raw Input Data
  </button>
  <button id="btn-steps"  class="tab-btn" onclick="showTab('steps')">
    <span class="tab-step">2</span>Cleansing Steps
  </button>
  <button id="btn-output" class="tab-btn" onclick="showTab('output')">
    <span class="tab-step">3</span>Clean Output
  </button>
</nav>

<!-- Tab 1: Raw Input -->
<div id="panel-input" class="tab-panel active">
  <div class="panel-title">Raw Input Data</div>
  <div class="panel-sub">
    {n_raw} records as received from the source system &mdash; before any cleansing.
    <em style="color:#ef5350">Red cells</em> indicate missing values.
  </div>
  {dirty}
</div>

<!-- Tab 2: Cleansing Steps -->
<div id="panel-steps" class="tab-panel">
  <div class="panel-title">Cleansing Steps &mdash; Record by Record</div>
  <div class="panel-sub">
    Click any card to expand / collapse. Fields highlighted in
    <span style="color:#ef9a9a">red</span> show the original dirty value;
    <span style="color:#a5d6a7">green</span> shows the corrected value.
  </div>
  <div class="toolbar">
    <button class="toolbar-btn" onclick="expandAll()">Expand All</button>
    <button class="toolbar-btn" onclick="collapseAll()">Collapse All</button>
  </div>
  {steps}
</div>

<!-- Tab 3: Clean Output -->
<div id="panel-output" class="tab-panel">
  <div class="panel-title">Clean Output Data</div>
  <div class="panel-sub">
    {n_clean} records after normalisation and deduplication.
  </div>
  {cleaned}
</div>

<script>{JS}</script>
</body>
</html>"""


def save_cleansing_report(
    raw_records: list,
    reports: list,
    clean_df: pd.DataFrame,
    output_path: str,
) -> None:
    html = generate_cleansing_html(raw_records, reports, clean_df)
    Path(output_path).write_text(html, encoding="utf-8")
    print(f"  Saved cleansing report -> {output_path}")
