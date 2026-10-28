# Original build brief (historical, superseded)

> **Read CLAUDE.md first. It is the current source of truth.** This is the brief the project started from on 2026-10-28.
> Two parts were changed during the build and must NOT be rebuilt from this file:
> - `attack/` (toy-key factoring and decryption of captured traffic) was dropped. Step 3 became real TLS 1.3 handshake evidence: legacy X25519 vs hybrid X25519MLKEM768, plus an ML-DSA-65 `pq-auth` service.
> - "attack succeeds on legacy, fails on migrated" in the definition of done was replaced by handshake-gate, downgrade-refusal and rollback tests.

---

You are building "Q-Shield Atlas", a hackathon product (PQC track, problem statement PQC-01). Work autonomously in this repo, in small verified steps. Python 3.12, conda env `pqc` is already active.

## Product in one line
Find vulnerable RSA/ECC in a system, schedule the migration optimally with QpiAI Opt, verify every wave, prove it with signed evidence, and show it in a 3D "exposure tower" (with a 2D fallback).

## Hard rules (honesty)
- Never invent API names. Before using qpiai-opt or QCloud, inspect the installed package (help(), dir(), docs/README, examples) and use only what exists. If something is unavailable, stop and tell me, then leave a clearly labelled stub.
- Never hard-code or claim results. Every number shown in the UI/README must come from a logged run (timestamp, inputs, solver output, job ID).
- No claim of quantum advantage. QAOA is a measured cross-check only.
- The small-key RSA break is a labelled toy stand-in for what a CRQC would do to RSA-2048. Say so in code comments, UI and README.
- Risk/effort scores and shelf-life values are assumptions; expose them in config and add a sensitivity test.

## Architecture (create these folders, one module each, communicating only through the JSON contracts below)
- capture/   lab TLS-like service with a deliberately small RSA key (64-128 bit), plus handshake/payload capture
- detect/    scan code, configs, certificates for RSA/ECC with file:line evidence; also probe live handshakes; report static-vs-live drift
- schedule/  QpiAI Opt MILP + baselines (first-come-first-served, greedy)
- gates/     per-wave checks: post-quantum handshake, compatibility test, tested rollback
- attack/    classical factoring of the toy key, decrypts captured traffic; replay mode that must FAIL against the migrated hybrid service
- ledger/    SHA-256 Merkle log; each entry signed with ML-DSA (use whatever is available: OpenSSL 3.5 / cryptography / liboqs-python; detect and fall back, note which); entries include run manifests (hashes of inputs, solver outputs, job IDs, timestamps)
- qaoa/      wave-selection QUBO solved by QAOA on QpiAI QCloud simulators, compared to exact optimum
- viz/       Three.js exposure tower + 2D fallback (default), reading only results.json
- tests/, run_demo.sh, README.md, CLAUDE.md

## Core model (schedule/)
Per asset i: shelf life X_i (years), effort w_i, risk weight r_i, dependencies. Migration completion time t_i (weeks -> years).
Exposure e_i >= X_i + t_i - Z, e_i >= 0, for each Z scenario (default 2030, 2032, 2035).
Minimise weighted sum of exposure; robust variant minimises worst-case across Z scenarios.
Constraints: each asset migrates exactly once; weekly effort <= capacity; a dependency migrates no later than what depends on it.
Report "exposure-years avoided" vs both baselines on the same data.

## QAOA (qaoa/)
Take the weekly wave-selection sub-problem (<= 16 binary vars): QUBO with penalties for capacity and dependency violations. Run QAOA p=1..3 with a classical optimiser on QpiAI simulators. Decode samples, discard infeasible, keep best feasible. Report approximation ratio vs exact optimum, probability of the optimal bitstring, job IDs. Labelled: measured cross-check, no advantage.

## JSON contracts (define in contracts/ with schemas and validate in tests)
1. capture.json: handshake bytes, ciphertext, service id
2. results.json: assets, waves, status, exposure-years per scenario, baselines, solver job IDs, attack results, ledger root
3. ledger entry: {index, type, payload_hash, prev_hash, sig_mldsa, ts}

## Build order (do not skip ahead; run tests after each step and commit)
1. schedule/ + baselines + tests (this is the safe core and the fallback)
2. detect/ on a sample repo of fake microservices + a mock-bank fixture; then on 1-2 real open-source microservice repos
3. capture/ + attack/ (attack succeeds on legacy service)
4. gates/ + migration to hybrid; attack replay must fail
5. ledger/ with signed run manifests; a tamper test (edit one row -> verification fails)
6. qaoa/ cross-check
7. viz/: tower height = remaining exposure-years, attacker beam cut after migration; 2D fallback works with no WebGL
8. run_demo.sh regenerates everything with one command; pin versions in requirements/lock file

## Definition of done
- `pytest` passes, including: attack succeeds on legacy, fails on migrated; ledger tamper detected; schedule feasible and never worse than baselines on the same data
- `./run_demo.sh` produces results.json and opens the viz
- README states every assumption, limit (simulator scale, local test ledger, toy-key attack) and how to rerun

Start by writing CLAUDE.md with these rules, then inspect the qpiai-opt and QCloud packages and report what the real APIs are before writing schedule/. Ask me only if blocked.