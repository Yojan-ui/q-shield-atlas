# Build history

Context for anyone (or any new Claude Code session) picking up this repo.

- **CLAUDE.md** at the repo root is the current rulebook. Read it first.
- `original-brief.md`: the brief the build started from on 2026-10-28. Historical; parts of it were dropped (see its header).
- `next-site-brief.md`: the planned showcase website (`site/`). Not started yet; paste it into Claude Code to begin.

## How the build went (2026-10-28, NITTE Meenakshi hackathon, PQC-01)
1. schedule/: MILP with local QpiAI Opt solves plus FCFS and greedy baselines. Platform mode is opt-in and capped.
2. detect/: static scan of fake multi-language services plus two real open-source repos (Online Boutique,
   OpenTelemetry Demo), every finding reviewed by hand in docs/detect_real_repos.md.
3. capture/: the toy-key attack was dropped. Replaced by real TLS 1.3 handshake evidence (legacy X25519 vs hybrid
   X25519MLKEM768) using OpenSSL 3.6.5.
4. gates/: PQ handshake gate, compatibility matrix, tested rollback, wave runner.
5. ledger/: ML-DSA-65 signed Merkle log with tamper tests; an ML-DSA-65 certificate added the `pq-auth` service.
6. qaoa/: QUBO cross-check on a local statevector simulator vs exact optimum and random sampling. QCloud is wired up
   but blocked until the account has an active subscription.
7. viz/: 2D chart (default) plus 3D exposure tower, all numbers read from results.json.
8. run_demo.sh, version pins, announce screen, offline report (out/report.html), DEMO.md, release v1.1-hackathon.
