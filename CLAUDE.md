# Q-Shield Atlas — working rules

Hackathon product, PQC track, problem statement PQC-01.
Find vulnerable RSA/ECC in a system, schedule the migration optimally with QpiAI Opt,
verify every wave, prove it with signed evidence, show it in a 3D exposure tower (2D fallback).

## Environment
- PQC TLS: `/opt/anaconda3/envs/pqc/bin/openssl` = OpenSSL 3.6.5 (conda-forge `openssl 3.6.5 h55eecbc_0`,
  pinned) with ML-KEM, X25519MLKEM768 and ML-DSA. System LibreSSL 3.3.6 and base-env OpenSSL 3.0.18
  have none of these; never use them for lab services.
- Python 3.12, conda env `pqc`: `conda activate pqc` (interpreter: `/opt/anaconda3/envs/pqc/bin/python`).
  The `base` env is Python 3.13 and lacks qpiai-opt / liboqs — never run project code with it.
- Credentials: `source .env.sh` exports `QPIAI_OPT_API_KEY` and `QCLOUD_API_KEY`.
  `.env.sh` is git-ignored. Never print, log, commit or embed keys in results/ledger.
- Verified API surface of qpiai-opt / qpiai-quantum: see `docs/qpiai_api_notes.md`.
  Re-check it there before using any QpiAI call; do not use names that are not listed.

## Honesty rules (non-negotiable)
1. Never invent API names. Inspect installed packages (source, `help()`, `dir()`, README) first.
   If something is unavailable: stop, tell the user, leave a clearly labelled stub.
2. Never hard-code or claim results. Every number in the UI / README comes from a logged run
   with timestamp, input hashes, solver output and job ID (or an explicit `null` + reason
   when the backend issues no job ID, e.g. local Opt solves).
3. No claim of quantum advantage. QAOA is a measured cross-check against the exact optimum only.
4. No key recovery, factoring or decryption anywhere in the project (user decision 2026-10-28).
   Quantum exposure is shown with handshake evidence only: classical-only sessions are labelled
   "HNDL-exposed: recorded traffic relies on classical key exchange". Never claim decryption.
5. Risk/effort scores and shelf-life values are assumptions: they live in config, are shown
   in the UI/README as assumptions, and have a sensitivity test.
6. QCloud platform runs must name a simulator device explicitly (`QpiAI-QSV-Simulator` etc.).
   The SDK's platform default is `QpiAI-Indus-1` (a QPU) — never rely on that default.
7. Platform modes (`mode="platform"`) can consume credits. Use local modes by default;
   platform runs only behind an explicit flag.

## Locked decisions (user, 2026-10-28)
- Scheduling MILP runs with free local QpiAI Opt solves. Local solves issue no job ID, so each
  solver run records `job_id: null`, a `job_id_reason` string, our own `run_id`, and SHA-256
  hashes of inputs and outputs. The README must document this fallback.
- QAOA: tune on the free local simulator first; then run a strictly capped number of cloud jobs
  on `QpiAI-QSV-Simulator` and log the real job IDs. Code must enforce a simulator device
  (reject `QpiAI-Indus-1` / unset device) before any platform call.

## Platform guardrails (user, 2026-10-28)
- Scheduling platform mode is opt-in only (`python -m schedule --platform`), 2 jobs per run,
  main plan only. Sensitivity, pytest and run_demo.sh stay local (`QSHIELD_FORBID_PLATFORM=1`).
- Print/log "Submitting N QpiAI jobs" before each submit; cap 10/UTC day in
  runs/platform_jobs.log unless `--allow-more`.
- Platform vs local objectives on the same input are both recorded; never silently pick one.
- Known blocker: Opt platform returns "no active storage quota found for organization".
  Do not retry until the user says the account is fixed.

## Architecture
Modules communicate only through the JSON contracts in `contracts/` (validated in tests).
- `capture/`  two local real-TLS-1.3 services via `openssl s_server` (legacy: X25519 only;
              hybrid: X25519MLKEM768 only) + handshake evidence via `openssl s_client -brief`
- `detect/`   static scan (code/config/certs, file:line evidence) + live handshake probe + drift
- `schedule/` QpiAI Opt MILP + baselines (FCFS, greedy)
- `gates/`    per-wave checks: PQ handshake (group allowlist), downgrade refused,
              compatibility test, tested rollback
- `ledger/`   SHA-256 Merkle log, entries signed with ML-DSA (backend detected and recorded)
- `qaoa/`     wave-selection QUBO (<=16 vars) via QAOA on QpiAI simulators vs exact optimum
- `viz/`      Three.js exposure tower + 2D fallback (default); reads only `results.json`
- `tests/`, `run_demo.sh`, `README.md`

Lab services bind 127.0.0.1 only, on free ports, as subprocesses with timeouts and clean shutdown.
Handshake capture uses `s_client -brief -msg`; never `-keylogfile`, never SSLKEYLOGFILE.
Strict mode is TLS 1.3 only (TLS 1.2 would let clients fall back to classical FFDHE).
Never report "applied"/"passed" without gate evidence; unmapped assets are not_verified_in_lab.

Contracts: `capture.json` (handshake sessions: service_id, negotiated_group, cipher, protocol,
cert_alg, transcript_sha256, timestamp; plus refused attempts), `results.json`, ledger entry
`{index, type, payload_hash, prev_hash, sig_mldsa, ts}`.

## Core model (schedule/)
Per asset i: shelf life X_i (years), effort w_i, risk weight r_i, dependencies.
Completion time t_i (weeks → years). For each scenario Z (default 2030, 2032, 2035):
e_i >= X_i + t_i − Z, e_i >= 0. Minimise weighted exposure; robust variant minimises worst case.
Constraints: each asset migrates exactly once; weekly effort <= capacity;
a dependency migrates no later than its dependents.
Report exposure-years avoided vs both baselines on the same data.

## Progress
- All 8 steps done; tagged v1.0-hackathon. One command: ./run_demo.sh (local only by default;
  --platform / --qcloud opt-in). Launch screen: ./announce.sh [--fast] [--json].
- Pins: requirements.txt (direct imports), requirements-lock.txt, environment.yml; OpenSSL path in
  config/lab.json ("openssl"), override with QSHIELD_OPENSSL.
- Report: python -m atlas report / ./report.sh -> out/report.html (offline, numbers from results.json
  only, signed into the ledger as report.html, then verified). Viz links to /out/report.html.
- Site: frontend in site/ (static, no Python package: `python -m site` is the stdlib module), backend
  `python -m atlas site` (atlas/site_server.py), read-only. While building it the outputs are frozen:
  no run_demo/schedule/gates/qaoa/ledger ingest/report, no ledger appends, and no `ledger verify` of
  the real ledger (it rewrites results.json); tests use temp copies only.
- Fresh-clone rule: running the demo must never modify tracked files (keys go to git-ignored keys/).
- viz serves only viz/ and out/results.json (never the repo: keys/ must stay unreachable). QCloud QAOA runs need the user's go-ahead (`python -m qaoa --qcloud`).
- viz/ must render qaoa.table rows generically: metrics when status == "ok", otherwise status_text.
  Never invent or zero-fill QCloud numbers.
- QCloud blocker: job creation needs an active QCloud subscription ("an active subscription is
  required to run jobs"). Do not retry --qcloud until the user says the account has one.
- QCloud (qpiai_quantum 0.3.0): Circuit.run(shots, device_name=...) blocks and returns JobResult
  (counts, job_id, credits_used). Only QpiAI-QSV-Simulator / QSV-Lite allowed; never Indus-1.
  Counts strings: qubit 0 rightmost; rz/rzz/rx = exp(-i t/2 P).
- Ledger signing: OpenSSL CLI ML-DSA-65 only; never fall back to classical signatures. Private key
  lives in git-ignored keys/ (0600); never print it, never commit it.
- Real-repo scans are read-only; clones live in git-ignored `.cache/repos/`.

## atlas_web (user, 2026-10-28; supersedes site/, which stays untouched)
- `python -m atlas_web`: login-protected full-stack UI that runs the pipeline CLIs as subprocesses in
  workspaces under git-ignored atlas_web/data/workspaces/<id>/{src,out,runs,config,keys}. The output freeze
  above protects only the repo snapshot: workspace runs are allowed; the `demo` workspace (repo out/ + runs/)
  is read-only. Workspace runs share runs/platform_jobs.log (--platform-log) so the daily cap stays global.
- Platform/QCloud controls are admin-only and disabled (blocker text shown) until the user flips the switch
  in config/atlas_web.json. Clones go to the workspace src/.
- v2.0-demo: THE LATTICE engine (atlas_web/static/js/engine/: one renderer, draws only inside [data-stage]),
  route scenes in js/scenes/, `python -m atlas_web export` (static, file://), crash recovery (INTERRUPTED runs).
  Verify with pytest, `node --test atlas_web/jstests/*.test.mjs`, `python tools/route_check.py`, `tools/bench_api.py`.

## Workflow
- Build order is fixed: schedule → detect → capture (handshake evidence) → gates → ledger → qaoa → viz → run_demo.
  Do not skip ahead.
- Small verified steps. Run `pytest` after each step, then commit.
- Definition of done: pytest green (legacy negotiates a classical group → PQ gate FAIL and
  HNDL-exposed; hybrid negotiates X25519MLKEM768 → gate PASS; classical-only client refused by
  the hybrid service; transition gives pq clients X25519MLKEM768 and flags classical ones
  HNDL-exposed; injected gate failure → rolled_back with config hash restored; corrupted snapshot →
  rollback_failed; no asset "applied" without gate evidence; no orphaned s_server; ledger tamper detected; schedule feasible and never worse than baselines); `./run_demo.sh` regenerates
  `results.json` and opens the viz; README states every assumption, limit and how to rerun.
