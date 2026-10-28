"""Display table for the QAOA cross-check: one row per (p, source), derived only from logged data.

QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage
claimed; the problem is small enough for brute force.

Row status: ok (metrics present) | failed | skipped | not_requested. Rows that are not ok carry
`metrics: null` and a `status_text` such as
  "skipped: no QCloud subscription (attempt logged, ledger #7)"
so a viewer never shows blanks or zeros for runs that did not happen. A later successful QCloud
run produces `ok` rows with metrics and job IDs through the same code path.
"""

KNOWN_REASONS = (
    ("active subscription is required", "no QCloud subscription"),
    ("not found. Please create the experiment", "QCloud experiment not found"),
    ("storage quota", "no storage quota"),
    ("PlatformRefused", "refused by the job guard"),
)


def short_reason(error: str | None) -> str:
    if not error:
        return "unknown error"
    for needle, short in KNOWN_REASONS:
        if needle in error:
            return short
    first = error.replace("earlier QCloud failure: ", "").splitlines()[0]
    return first if len(first) <= 80 else first[:77] + "..."


def _logged_suffix(run_id: str, ledger_index: int | None) -> str:
    if ledger_index is not None:
        return f"(attempt logged, ledger #{ledger_index})"
    return f"(attempt logged in runs/{run_id}/; not yet signed into the ledger)"


def build_table(section: dict, ledger_index: int | None = None) -> list[dict]:
    runs = section["runs"]
    reps = sorted({r["p"] for r in runs if r["source"] == "local"})
    jobs = {j["p"]: j for j in section["qcloud"].get("jobs", [])}
    device = section["qcloud"].get("device", "QCloud")
    rows = []

    def ok_row(r):
        return {"p": r["p"], "source": r["source"], "status": "ok", "status_text": None, "backend": r["backend"],
                "shots": r["shots"], "job_ids": r["job_ids"], "metrics": r["metrics"]}

    for p in reps:
        rows.append(ok_row(next(r for r in runs if r["source"] == "local" and r["p"] == p)))
        cloud = next((r for r in runs if r["source"] == "qcloud" and r["p"] == p), None)
        if cloud is not None:
            rows.append(ok_row(cloud))
            continue
        job = jobs.get(p)
        if not section["qcloud"].get("requested") or job is None:
            status, text = "not_requested", "not run: QCloud sampling is opt-in (python -m qaoa --qcloud)"
        else:
            status = job["status"] if job["status"] in ("failed", "skipped") else "failed"
            text = f"{status}: {short_reason(job.get('error'))} {_logged_suffix(section['run_id'], ledger_index)}"
        rows.append({"p": p, "source": "qcloud", "status": status, "status_text": text, "backend": device,
                     "shots": None, "job_ids": [j for j in [job.get("job_id")] if j] if job else [], "metrics": None})
    rows += [ok_row(r) for r in runs if r["source"] == "random"]
    return rows
