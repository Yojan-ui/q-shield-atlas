# Q-Shield Atlas — working rules

Hackathon product, PQC track, problem statement PQC-01.
Find vulnerable RSA/ECC in a system, schedule the migration optimally with QpiAI Opt,
verify every wave, prove it with signed evidence, show it in a 3D exposure tower (2D fallback).

## Environment
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
4. The small-key RSA break is a labelled toy stand-in for what a CRQC would do to RSA-2048.
   Say so in code comments, UI and README.
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

## Architecture
Modules communicate only through the JSON contracts in `contracts/` (validated in tests).
- `capture/`  lab TLS-like service with a deliberately small RSA key (64–128 bit) + capture
- `detect/`   static scan (code/config/certs, file:line evidence) + live handshake probe + drift
- `schedule/` QpiAI Opt MILP + baselines (FCFS, greedy)
- `gates/`    per-wave checks: PQ handshake, compatibility test, tested rollback
- `attack/`   toy factoring + decrypt of captured legacy traffic; replay must FAIL on hybrid
- `ledger/`   SHA-256 Merkle log, entries signed with ML-DSA (backend detected and recorded)
- `qaoa/`     wave-selection QUBO (<=16 vars) via QAOA on QpiAI simulators vs exact optimum
- `viz/`      Three.js exposure tower + 2D fallback (default); reads only `results.json`
- `tests/`, `run_demo.sh`, `README.md`

Contracts: `capture.json`, `results.json`, ledger entry
`{index, type, payload_hash, prev_hash, sig_mldsa, ts}`.

## Core model (schedule/)
Per asset i: shelf life X_i (years), effort w_i, risk weight r_i, dependencies.
Completion time t_i (weeks → years). For each scenario Z (default 2030, 2032, 2035):
e_i >= X_i + t_i − Z, e_i >= 0. Minimise weighted exposure; robust variant minimises worst case.
Constraints: each asset migrates exactly once; weekly effort <= capacity;
a dependency migrates no later than its dependents.
Report exposure-years avoided vs both baselines on the same data.

## Workflow
- Build order is fixed: schedule → detect → capture+attack → gates → ledger → qaoa → viz → run_demo.
  Do not skip ahead.
- Small verified steps. Run `pytest` after each step, then commit.
- Definition of done: pytest green (attack succeeds on legacy / fails on migrated; ledger tamper
  detected; schedule feasible and never worse than baselines); `./run_demo.sh` regenerates
  `results.json` and opens the viz; README states every assumption, limit and how to rerun.
