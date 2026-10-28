"""Self-contained offline HTML report (out/report.html) built from results.json, the ledger and runs/.

All data is rendered into the file at build time (works over file://, no fetch, no CDN, no external
URLs). Every number is a <span class="n" data-v="..."> taken from results.json with a provenance
tag (run_id / job_id). Missing data renders "not yet run". The footer carries the SHA-256 of the
file computed with that footer value set to 64 zeros, so anyone can recompute it.
"""

import hashlib
import html
import json
import re
import subprocess
from pathlib import Path

from contracts import validate
from contracts.manifest import sha256_json

REPO = Path(__file__).resolve().parent.parent
NOT_YET_RUN = "not yet run"
ZERO_HASH = "0" * 64
QAOA_LABEL = "measured cross-check, no quantum advantage"
PLACEHOLDER = "@@REPORT_SHA256@@"

e = html.escape


def short(x, n=8):
    return x[:n] if isinstance(x, str) and x else NOT_YET_RUN


def n(value, prov="", digits=3):
    """A number from results.json with a provenance tag; None -> 'not yet run'."""
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return f'<span class="missing">{NOT_YET_RUN}</span>'
    text = str(value) if isinstance(value, int) else f"{value:.{digits}f}"
    tag = f'<sup class="prov">{e(prov)}</sup>' if prov else ""
    return f'<span class="n" data-v="{value!r}">{text}</span>{tag}'


def missing(what=NOT_YET_RUN):
    return f'<p class="missing">{e(what)}</p>'


def table(headers, rows, cls=""):
    head = "".join(f"<th>{e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def md_inline(text: str) -> str:
    t = e(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", t)


def readme_bullets(heading: str) -> list[str]:
    text = (REPO / "README.md").read_text() if (REPO / "README.md").exists() else ""
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^#)", text, re.S | re.M)
    if not m:
        return []
    items, cur = [], None
    for line in m.group(1).splitlines():
        if line.startswith("- "):
            cur = line[2:].strip()
            items.append(cur)
        elif line.startswith("  ") and items:
            items[-1] += " " + line.strip()
    return items


def doc_bullets(path: Path, heading: str) -> list[str]:
    if not path.exists():
        return []
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", path.read_text(), re.S | re.M)
    items: list[str] = []
    for line in (m.group(1).splitlines() if m else []):
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif line.startswith("  ") and items:
            items[-1] += " " + line.strip()
    return items


# ---------------- checks ----------------

def git_commit() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO, capture_output=True, text=True).stdout.strip()
        return sha + (" (with uncommitted changes)" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown (not a git checkout)"


def solver_manifest_checks(r: dict, runs_dir: Path) -> list[tuple[str, bool]]:
    out = []
    for run in r.get("solver_runs", []):
        d = runs_dir / run["run_id"]
        ok = (d / "manifest.json").exists() and (d / "solver_output.json").exists() and \
            sha256_json(json.loads((d / "solver_output.json").read_text())) == run["output_sha256"]
        out.append((f"runs/{run['run_id']}: manifest present, solver output hash matches", ok))
    return out


def ledger_file_root(r: dict, root: Path = REPO) -> tuple[str | None, int | None]:
    if not r.get("ledger"):
        return None, None
    from ledger.log import canonical, read_entries
    from ledger.merkle import MerkleTree

    path = root / r["ledger"]["ledger_ref"]
    if not path.exists():
        return None, None
    entries = read_entries(path)
    return MerkleTree([canonical(x) for x in entries]).root(), len(entries)


def checks(r: dict | None, runs_dir: Path, ledger_root: Path = REPO) -> list[tuple[str, bool]]:
    if not r:
        return [("out/results.json present", False)]
    out = []
    try:
        validate("results", r)
        out.append(("results.json matches contracts/results.schema.json", True))
    except Exception:
        out.append(("results.json matches contracts/results.schema.json", False))
    led, ver = r.get("ledger"), r.get("ledger_verification")
    out.append(("ledger verified for the anchored root",
                bool(led and ver and ver["ok"] and ver["root"] == led["root"] and ver["entries_checked"] == led["entry_count"])))
    root, count = ledger_file_root(r, ledger_root)
    out.append(("ledger file recomputes to the anchored Merkle root", bool(led and root == led["root"] and count == led["entry_count"])))
    out.append(("every MILP stage proven optimal", bool(r.get("solver_runs")) and all(x.get("termination") == "optimal" for x in r["solver_runs"])))
    out += solver_manifest_checks(r, runs_dir)
    return out


# ---------------- sections ----------------

def sec_summary(r, chk, commit):
    ok = all(c for _, c in chk)
    rows = [[("✔" if c else "✖"), e(t)] for t, c in chk]
    return f"""
<p>Q-Shield Atlas finds the RSA, ECC and DH a cryptographically relevant quantum computer would break, schedules
the migration with QpiAI Opt to minimise harvest-now-decrypt-later exposure, verifies every wave on real TLS 1.3
lab services, and proves each run with an ML-DSA-65-signed, hash-chained ledger.</p>
<div class="kv"><span>results generated</span><span>{e(r.get('generated_at', NOT_YET_RUN)) if r else NOT_YET_RUN}</span>
<span>git commit</span><code>{e(commit)}</code>
<span>overall</span><span class="{'pass' if ok else 'fail'} big">{'PASS' if ok else 'FAIL'}</span></div>
{table(['', 'check'], rows, 'checks')}"""


def sec_inventory(r):
    d = r.get("detect") if r else None
    if not d:
        return missing()
    prov = f"detect {short(d['run_id'])}"
    s = d["summary"]
    fam_use = s.get("by_family_use")
    if fam_use:
        uses = sorted({u for v in fam_use.values() for u in v})
        rows = [[e(f)] + [n(fam_use[f].get(u), prov) if u in fam_use[f] else "–" for u in uses] + [n(s["by_family"][f], prov)] for f in fam_use]
        breakdown = table(["algorithm family"] + uses + ["total"], rows)
    else:
        breakdown = missing("usage breakdown not yet run (rerun detect)")
    ev_rows = [[f"<code>{e(f['file'])}:{n(f['line'], '', 0)}</code>", e(f["family"]), e(f["use"]), e(f["rule"]), f"<code>{e(f['snippet'])}</code>"]
               for f in d["findings"]]
    drift_rows = [[e(p["service"]), e(p["endpoint"]), e(p["live"].get("group") or NOT_YET_RUN), e(p["live"].get("cert_algorithm") or NOT_YET_RUN),
                   "<br>".join(f"<strong>{e(x['kind'])}</strong> ({e(x['severity'])}): {e(x['detail'])}" for x in p["drift"]) or "none"]
                  for p in d["probes"]]
    misses = doc_bullets(REPO / "docs" / "detect_real_repos.md", "Known remaining gaps")
    return f"""
<div class="kv"><span>files scanned</span><span>{n(d['files_scanned'], prov)}</span>
<span>vulnerable findings</span><span>{n(s['vulnerable_findings'], prov)}</span>
<span>PQC findings</span><span>{n(s['pqc_findings'], prov)}</span>
<span>assets to migrate</span><span>{n(d['inventory']['assets'], prov)}</span>
<span>not vulnerable</span><span>{e(', '.join(d['inventory']['not_vulnerable']) or 'none')}</span>
<span>tree SHA-256</span><code>{e(d['tree_sha256'])}</code></div>
<h3>Findings by algorithm and usage</h3>{breakdown}
<details><summary>file:line evidence (expand)</summary>{table(['location', 'family', 'use', 'rule', 'snippet'], ev_rows, 'small')}</details>
<h3>Static vs live drift</h3>{table(['service', 'endpoint', 'live group', 'live cert', 'drift'], drift_rows) if drift_rows else missing('no live probe recorded')}
<h3>Known misses</h3><ul>{''.join(f'<li>{md_inline(m)}</li>' for m in misses) or '<li>' + NOT_YET_RUN + '</li>'}</ul>"""


def chart_svg(r, scenario):
    plans = [("optimised", r.get("exposure")), ("FCFS", (r.get("baselines") or {}).get("fcfs")), ("greedy", (r.get("baselines") or {}).get("greedy"))]
    series = {}
    for label, p in plans:
        s = next((x for x in (p or {}).get("remaining_by_week", []) if x["scenario"] == scenario), None)
        if s is None:
            return missing()
        series[label] = s["points"]
    W, H, L, R, T, B = 340, 200, 40, 10, 14, 30
    vals = [pt["exposure_years"] for pts in series.values() for pt in pts]
    ymax = max(vals) or 1
    wmax = max(pt["week"] for pts in series.values() for pt in pts) or 1
    x = lambda w: L + (W - L - R) * w / wmax
    y = lambda v: T + (H - T - B) * (1 - v / ymax)
    style = {"optimised": ("#2563eb", ""), "FCFS": ("#c2410c", "6 4"), "greedy": ("#6b7280", "2 3")}
    parts = [f'<line x1="{L}" y1="{H-B}" x2="{W-R}" y2="{H-B}" stroke="#bbb"/><line x1="{L}" y1="{T}" x2="{L}" y2="{H-B}" stroke="#bbb"/>']
    for w in sorted({pt["week"] for pts in series.values() for pt in pts}):
        parts.append(f'<text x="{x(w):.1f}" y="{H-B+13}" text-anchor="middle">{w}</text>')
    peak = max(vals)
    parts.append(f'<text x="{L-3}" y="{y(peak)+4:.1f}" text-anchor="end">{peak:.1f}</text>')
    for label, pts in series.items():
        c, d = style[label]
        parts.append(f'<polyline fill="none" stroke="{c}" stroke-width="2" stroke-dasharray="{d}" points="' +
                     " ".join(f"{x(p['week']):.1f},{y(p['exposure_years']):.1f}" for p in pts) + '"/>')
    parts.append(f'<text x="{(L+W-R)/2}" y="{H-3}" text-anchor="middle">week</text>')
    legend = " ".join(f'<span style="color:{style[k][0]}">■ {k}</span>' for k in series)
    return f'<figure><svg viewBox="0 0 {W} {H}" role="img" aria-label="remaining exposure-years, {e(scenario)}">{"".join(parts)}</svg><figcaption>{e(scenario)} · {legend}</figcaption></figure>'


def sec_plan(r):
    if not r or not r.get("exposure"):
        return missing()
    runs = {x["run_id"]: x for x in r.get("solver_runs", [])}
    pb = r["exposure"].get("produced_by", {})
    ids = pb.get("run_ids", [])
    jobs = sorted({runs[i]["job_id"] or "none" for i in ids if i in runs})
    prov = f"run {', '.join(short(i) for i in ids)} · job {', '.join(jobs) or NOT_YET_RUN}"
    wave_rows = [[n(w["week"], "", 0), e(", ".join(w["assets"])), n(w["effort_days"], "", 1), e(w["status"])] for w in r.get("waves", [])]
    base = r.get("baselines") or {}
    per = []
    for i, sc in enumerate(r["exposure"]["per_scenario"]):
        f = base.get("fcfs", {}).get("per_scenario", [{}] * (i + 1))[i]
        g = base.get("greedy", {}).get("per_scenario", [{}] * (i + 1))[i]
        av_f = (r.get("avoided") or {}).get("vs_fcfs", [{}] * (i + 1))[i]
        av_g = (r.get("avoided") or {}).get("vs_greedy", [{}] * (i + 1))[i]
        per.append([e(sc["scenario"]), n(sc["exposure_years"], prov), n(f.get("exposure_years"), "fcfs"), n(g.get("exposure_years"), "greedy"),
                    n(av_f.get("exposure_years_avoided"), prov), n(av_g.get("exposure_years_avoided"), prov)])
    reasons = sorted({runs[i].get("job_id_reason") or "" for i in ids if i in runs} - {""})
    charts = "".join(chart_svg(r, s["scenario"]) for s in r["exposure"]["per_scenario"])
    return f"""
<div class="kv"><span>solver</span><span>{e(pb.get('solver', NOT_YET_RUN))}</span>
<span>run_id</span><code>{e(', '.join(ids) or NOT_YET_RUN)}</code>
<span>job_id</span><span>{e(', '.join(jobs) or NOT_YET_RUN)}{(' (' + e('; '.join(reasons)) + ')') if reasons else ''}</span>
<span>objective</span><span>{e(r['exposure'].get('objective', NOT_YET_RUN))}</span></div>
<h3>Waves</h3>{table(['week', 'assets', 'effort (days)', 'status'], wave_rows) if wave_rows else missing()}
<h3>Exposure-years per CRQC scenario</h3>{table(['scenario', 'optimised', 'FCFS', 'greedy', 'avoided vs FCFS', 'avoided vs greedy'], per)}
<div class="charts">{charts}</div>
<p class="note">The chart and table show raw (unweighted) exposure-years. The optimiser minimises the risk-weighted,
scenario-weighted total, so in some weeks its unweighted curve sits above a baseline.</p>"""


def sec_handshake(r):
    he = r.get("handshake_evidence") if r else None
    g = (r or {}).get("gates") or {}
    if not he:
        return missing()
    by = lambda lst, sid: next((x for x in (lst or []) if x["service_id"] == sid), {})
    prov = f"capture {short(he['run_id'])}"
    rows = [[e(s["service_id"]), e(s["negotiated_group"]) + (f'<div class="warn">{e(s["label"])}</div>' if s.get("label") else ""),
             e(by(g.get("pq_handshake"), s["service_id"]).get("result", NOT_YET_RUN)), e(s.get("auth_alg", NOT_YET_RUN)),
             e(by(g.get("pq_auth"), s["service_id"]).get("result", NOT_YET_RUN)), f"<code>{e(s['transcript_sha256'])}</code>"] for s in he["sessions"]]
    mtx = []
    for m in g.get("compat_matrix", []):
        for c in m["cells"]:
            exp = c["expected"]["expect"] + (" " + c["expected"]["group"] if "group" in c["expected"] else "")
            act = (f"connect {c['actual']['negotiated_group']} {c['actual']['protocol']}" if c["actual"]["connected"] else "refused")
            mtx.append([e(m["mode"]), e(c["client"]), e(exp), e(act), f'<span class="{c["result"].replace("HNDL-exposed", "hndl")}">{e(c["result"])}</span>',
                        f"<code>{e(short(c['transcript_sha256'], 16))}</code>"])
    return f"""<p>{e(he['note'])} <span class="prov">{e(prov)} · {e(he['openssl_version'])}</span></p>
{table(['service', 'key exchange', 'pq_handshake', 'authentication', 'pq_auth', 'transcript SHA-256'], rows, 'small')}
<h3>Compatibility matrix</h3>{table(['mode', 'client', 'expected', 'actual', 'result', 'transcript'], mtx, 'small') if mtx else missing()}"""


def sec_waves(r):
    g = (r or {}).get("gates") or {}
    if not g.get("wave_counts"):
        return missing()
    prov = f"wave run {short(g.get('wave_run_id'))}"
    counts = table(["wave status", "waves"], [[e(k), n(v, prov)] for k, v in g["wave_counts"].items()]) + \
        table(["asset status", "assets"], [[e(k), n(v, prov)] for k, v in g["wave_asset_counts"].items()])
    fr = g.get("forced_rollback")
    if fr:
        failing = [c for c in fr["gates"].get("compat", {}).get("cells", []) if c["result"] == "FAIL"]
        rb = f"""<div class="kv"><span>transition</span><span>{e(fr['from_mode'])} → {e(fr['to_mode'])} (policy deliberately requires classical clients)</span>
<span>status</span><strong>{e(fr['status'])}</strong>
<span>failing gate</span><span>{e('; '.join(c['client'] + ': ' + c['reason'] for c in failing) or 'none')}</span>
<span>snapshot SHA-256</span><code>{e(fr['snapshot_sha256'])}</code>
<span>applied SHA-256</span><code>{e(fr['applied_config_sha256'])}</code>
<span>restored SHA-256</span><code>{e(fr.get('restored_config_sha256', NOT_YET_RUN))}</code>
<span>restored = snapshot</span><span>{'✔' if fr.get('restored_config_sha256') == fr['snapshot_sha256'] else '✖'}</span>
<span>health check</span><span>{e(fr.get('health_check', {}).get('result', NOT_YET_RUN))} ({e(str(fr.get('health_check', {}).get('negotiated_group')))})</span></div>"""
    else:
        rb = missing()
    return f"{counts}<h3>Forced rollback</h3>{rb}"


def sec_ledger(r, root: Path = REPO):
    led = (r or {}).get("ledger")
    if not led:
        return missing()
    ver = r.get("ledger_verification")
    vtext = (NOT_YET_RUN if not ver else ("✔ verified" if ver["ok"] and ver["root"] == led["root"] else
             f"✖ {ver['first_failure']}" if not ver["ok"] else "stale: verified a different root"))
    from ledger.log import canonical, read_entries
    from ledger.merkle import MerkleTree, verify_proof

    proof_html = missing()
    path = root / led["ledger_ref"]  # ledger_ref is relative to the ledger root (repo or workspace)
    q = r.get("qaoa") or {}
    idx = q.get("ledger_index")
    if path.exists() and idx is not None:
        entries = read_entries(path)[: led["entry_count"]]
        items = [canonical(x) for x in entries]
        tree = MerkleTree(items)
        proof = tree.inclusion_proof(idx)
        ok = verify_proof(items[idx], idx, len(items), proof, led["root"])
        proof_html = f"""<p>Inclusion proof for entry #{n(idx, 'qaoa.run', 0)} (<code>{e(entries[idx]['type'])}</code>) in a tree of {n(led['entry_count'], '', 0)} entries: <strong>{'verifies' if ok else 'FAILS'}</strong></p>
<ol class="mono">{''.join(f'<li>{e(h)}</li>' for h in proof)}</ol>"""
    return f"""<div class="kv"><span>entries</span><span>{n(led['entry_count'], 'ledger', 0)}</span>
<span>Merkle root (RFC 6962)</span><code>{e(led['root'])}</code>
<span>signature</span><span>{e(led['alg'])} via {e(led['backend'])}</span>
<span>public key SHA-256</span><code>{e(led['pubkey_fp'])}</code>
<span>verify result</span><span>{e(vtext)} {('<span class="prov">' + e(ver['ts']) + '</span>') if ver else ''}</span></div>
{proof_html}
<p>Re-verify: <code>python -m ledger verify</code> · inclusion proof: <code>python -m ledger proof {e(str(idx) if idx is not None else 'N')}</code></p>"""


def sec_qaoa(r):
    q = (r or {}).get("qaoa")
    if not q or not q.get("table"):
        return missing()
    rows = []
    for row in q["table"]:
        prov = f"run {short(q['run_id'])}" + (f" · job {', '.join(row['job_ids'])}" if row["job_ids"] else "")
        lead = [e("–" if row["p"] is None else str(row["p"])), e(row["source"])]
        if row["status"] == "ok":
            m = row["metrics"]
            rows.append(lead + [n(m[k], prov, 4) for k in ("feasible_fraction", "approximation_ratio", "energy_ratio", "p_optimal", "p_optimal_assets")])
        else:
            rows.append(lead + [f'<span class="missing">{e(row["status_text"])}</span>', "", "", "", ""])
    return f"""<p class="label">{QAOA_LABEL}</p>
<p>Exact optimum (brute force): objective {n(q['exact']['objective'], 'run ' + short(q['run_id']), 6)}, assets {e(', '.join(q['exact']['assets']))}</p>
{table(['p', 'source', 'feasible', 'approx. ratio', 'energy ratio', 'P(opt)', 'P(opt set)'], rows)}
<p class="note">{e(q['label'])}</p>"""


def sec_assumptions(r):
    a = (r or {}).get("assumptions")
    if not a:
        return missing()
    prov = f"config sha {short(a.get('sha256'))}"
    sc = table(["scenario", "CRQC year", "weight"], [[e(s["name"]), n(s["year"], prov, 0), n(s["weight"], prov, 2)] for s in a.get("scenarios", [])])
    dc = table(["data class", "shelf life (years)", "risk weight"],
               [[e(k), n(v["shelf_life_years"], prov, 1), n(v["risk_weight"], prov, 1)] for k, v in a.get("data_classes", {}).items()])
    ef = table(["asset kind", "effort (engineer-days)"], [[e(k), n(v, prov, 0)] for k, v in a.get("effort_days_by_kind", {}).items()])
    cap = f"""<div class="kv"><span>start year</span><span>{n(a.get('start_year'), prov, 1)}</span>
<span>capacity per week (days)</span><span>{n(a.get('capacity_days_per_week'), prov, 0)}</span>
<span>objective</span><span>{e(a.get('objective', NOT_YET_RUN))}</span></div>"""
    limits = "".join(f"<li>{md_inline(x)}</li>" for x in readme_bullets("Assumptions and limits"))
    return f"<p class=\"note\">{e(a.get('label', ''))}</p>{cap}{sc}{dc}{ef}<h3>Limits (from README)</h3><ul>{limits or '<li>' + NOT_YET_RUN + '</li>'}</ul>"


def sec_reproduce(r):
    pins = [l.strip() for l in (REPO / "requirements.txt").read_text().splitlines() if l.strip() and not l.startswith("#")] \
        if (REPO / "requirements.txt").exists() else []
    lab = json.loads((REPO / "config" / "lab.json").read_text()).get("openssl", {}) if (REPO / "config" / "lab.json").exists() else {}
    he = (r or {}).get("handshake_evidence") or {}
    return f"""<pre>conda env create -f environment.yml && conda activate pqc
export QPIAI_OPT_API_KEY=...
./run_demo.sh --no-open        # local only; --platform / --qcloud are opt-in and guarded
python -m ledger verify
./report.sh                    # rebuild this report</pre>
<div class="kv"><span>OpenSSL used</span><span>{e(he.get('openssl_version', lab.get('version', NOT_YET_RUN)))}</span>
<span>OpenSSL binary</span><code>{e(lab.get('path', NOT_YET_RUN))}</code>
<span>pins (requirements.txt)</span><code>{e(' · '.join(pins) or NOT_YET_RUN)}</code></div>"""


CSS = """
:root{--ink:#16191d;--muted:#5c6570;--line:#d6d9dd;--bg:#fff;--pass:#15803d;--fail:#b91c1c;--hndl:#b45309}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
.banner{background:#fff4cc;color:#4d3a00;padding:8px 20px;font-weight:600;border-bottom:1px solid var(--line)}
main{max-width:1100px;margin:0 auto;padding:16px 20px 40px}h1{font-size:24px;margin:8px 0 2px}h2{font-size:17px;margin:28px 0 8px;border-bottom:2px solid var(--ink);padding-bottom:3px}
h3{font-size:14px;margin:16px 0 6px}.sub{color:var(--muted);margin:0 0 6px}
table{border-collapse:collapse;width:100%;margin:6px 0 10px}th,td{text-align:left;padding:4px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}table.small{font-size:12px}code,.mono{font:11.5px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:3px 14px;margin:8px 0}.kv>span:nth-child(odd){color:var(--muted)}
.n{font-variant-numeric:tabular-nums}.prov{color:var(--muted);font-size:9.5px;margin-left:2px}
.missing{color:var(--muted);font-style:italic}.pass{color:var(--pass);font-weight:700}.fail{color:var(--fail);font-weight:700}.big{font-size:18px}
.PASS{color:var(--pass);font-weight:600}.FAIL{color:var(--fail);font-weight:600}.hndl,.warn{color:var(--hndl)}.warn{font-size:11px}
.note{color:var(--muted);font-size:12px}.label{font-weight:700;color:var(--hndl)}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:8px}figure{margin:0}svg{width:100%;height:auto}svg text{font-size:10px;fill:var(--muted)}
figcaption{font-size:11px;color:var(--muted)}details summary{cursor:pointer;color:#1d4ed8;margin:6px 0}pre{background:#f4f4f2;padding:10px;overflow-x:auto;font-size:12px}
footer{margin-top:30px;border-top:1px solid var(--line);padding-top:8px;color:var(--muted);font-size:11px}
@media print{.banner{position:static}main{max-width:none;padding:0 6mm}h2{break-after:avoid}table,figure,.kv,pre{break-inside:avoid}
details>summary{display:none}a{color:inherit;text-decoration:none}body{font-size:11px}@page{margin:14mm}}
"""
JS = "window.addEventListener('beforeprint',()=>document.querySelectorAll('details').forEach(d=>d.open=true));"
BANNER = ("Lab demo · local TLS lab services on 127.0.0.1 · local single-key test ledger (no public timestamping) · "
          "simulator-scale QAOA, no quantum advantage claimed · risk, effort and shelf-life values are assumptions (config/assumptions.json)")


def build_html(r: dict | None, runs_dir: Path = REPO / "runs", commit: str | None = None, ledger_root: Path = REPO) -> str:
    commit = commit or git_commit()
    chk = checks(r, runs_dir, ledger_root)
    sections = [
        ("1. Summary", sec_summary(r, chk, commit)),
        ("2. Inventory (detect)", sec_inventory(r)),
        ("3. Migration plan (schedule)", sec_plan(r)),
        ("4. Handshake evidence", sec_handshake(r)),
        ("5. Waves & rollback", sec_waves(r)),
        ("6. Signed ledger", sec_ledger(r, ledger_root)),
        ("7. QAOA cross-check", sec_qaoa(r)),
        ("8. Assumptions & limits", sec_assumptions(r)),
        ("9. Reproduce", sec_reproduce(r)),
    ]
    body = "".join(f'<section><h2>{e(t)}</h2>{c}</section>' for t, c in sections)
    gen = e((r or {}).get("generated_at", NOT_YET_RUN))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Q-Shield Atlas report</title><style>{CSS}</style></head><body>
<div class="banner">{e(BANNER)}</div><main>
<h1>Q-Shield Atlas</h1><p class="sub">Track: Post-Quantum Cryptography · PQC-01 · report built from out/results.json ({gen}), the signed ledger and runs/ manifests</p>
{body}
<footer>Report SHA-256 (computed with this value set to 64 zeros): <code>{PLACEHOLDER}</code><br>
Recompute: replace the value above with 64 zeros and run <code>shasum -a 256</code> on the file. The exact file is also signed into the ledger
(entry type <code>report.html</code>).</footer></main><script>{JS}</script></body></html>"""


FOOTER_HASH = "Report SHA-256 (computed with this value set to 64 zeros): <code>"


def finalize(html_text: str) -> tuple[str, str]:
    """Embed the self-hash: SHA-256 of the document with the footer hash field set to 64 zeros."""
    if html_text.count(PLACEHOLDER) != 1:
        raise ValueError("report must contain exactly one hash placeholder")
    zeroed = html_text.replace(FOOTER_HASH + PLACEHOLDER, FOOTER_HASH + ZERO_HASH)
    digest = hashlib.sha256(zeroed.encode("utf-8")).hexdigest()
    return zeroed.replace(FOOTER_HASH + ZERO_HASH, FOOTER_HASH + digest, 1), digest


def self_hash_ok(html_text: str) -> bool:
    m = re.search(re.escape(FOOTER_HASH) + r"([0-9a-f]{64})", html_text)
    if not m:
        return False
    zeroed = html_text.replace(m.group(0), FOOTER_HASH + ZERO_HASH, 1)
    return hashlib.sha256(zeroed.encode("utf-8")).hexdigest() == m.group(1)
