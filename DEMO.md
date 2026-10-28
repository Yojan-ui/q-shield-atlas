# Q-Shield Atlas: 2-minute live demo runbook

Pitch flow: problem → announce → detect → schedule → handshakes → ledger tamper → QAOA → close.
Total budget: **120 s**. Every number below is from the current `out/results.json` and ledger,
which are the same values as the `results.json` attached to release `v1.1-hackathon`. The source
of each number is in an HTML comment next to it (view the raw file to see them).

<!-- Snapshot: ledger 52 entries, root e8b64d3a7cdb5f6d7c5b2c9accf50d9d26c9aa024f83f1916d482cf2e1d7c616 (results.json: ledger.entry_count, ledger.root).
     Plan, handshake and QAOA numbers are deterministic, so a rerun of ./run_demo.sh reproduces them; run_ids, ports,
     transcript hashes, the ledger entry count and root change on every rerun. Do not rerun run_demo.sh right before
     the demo: the viz, announce and report all read the same snapshot. -->

## Pre-demo checklist (10 s, before you walk up)

- [ ] Terminal: font at least 18 pt (Cmd +), window wide (at least 150 columns), `cd` into the repo, `conda activate pqc`.
- [ ] Close other browser tabs; turn on Do Not Disturb; plug in the charger (battery saver throttles the run).
- [ ] Port and processes free: `pgrep -fl "python -m viz|s_server" || echo clear`; should print `clear`.
- [ ] Second terminal: `python -m viz`. It binds 127.0.0.1 on a free port and opens the browser on the 2D view; leave that tab open.
- [ ] In the demo terminal: `export DEMO=$(mktemp -d)` (scratch dir for the live commands and the ledger copy).
- [ ] Fallback ready, offline: `gh release download v1.1-hackathon -R Yojan-ui/q-shield-atlas -p q-shield-atlas-report.html -D ~/Desktop --clobber`

---

## 1. Problem (10 s)

**Command:** none (title slide or the viz banner).
**On screen:** the viz banner: "Lab demo · local test ledger · simulator-scale QAOA · …".
**Say:** "Every RSA and ECC key exchange recorded today can be decrypted once a quantum computer
arrives, so the real question for a bank is which systems to move first, and how to prove each move worked."

## 2. Announce (15 s)

**Command:**
```bash
./announce.sh --fast
```
**On screen:** the Q-SHIELD ATLAS banner, "Track: Post-Quantum Cryptography · PQC-01", 9 modules all ✔ <!-- out/pytest-junit.xml via atlas.announce.module_status; 249 tests passed in the last full run (pytest at commit d7545a3) -->,
16 assets to migrate <!-- results.json: detect.inventory.assets = 16 -->, the handshake table and the ledger: 52 entries, ✔ verified <!-- results.json: ledger.entry_count = 52; ledger_verification.ok = true -->.
**Say:** "One command regenerates everything, and this screen is computed from the signed results, not typed in: every module is built and tested, and the ledger verifies."

## 3. Detect (15 s)

**Command:**
```bash
python -m detect --lab-probe web-gw=legacy --out-dir "$DEMO" --runs "$DEMO/runs"
```
**On screen** (0.6 s <!-- rehearsal timing on the demo laptop, 2026-10-28 -->):
```
scanned 37 files: 29 vulnerable, 2 PQC findings
inventory: 16 assets to migrate; not vulnerable: ['status-page']
probe web-gw 127.0.0.1:<port>: group=X25519 cert=RSA-2048 drift=['pqc_claimed_not_negotiated']
```
<!-- results.json: detect.files_scanned = 37; detect.summary.vulnerable_findings = 29; detect.summary.pqc_findings = 2;
     detect.inventory.assets = 16; detect.inventory.not_vulnerable = ["status-page"]; detect.drift_count = 1;
     detect.probes[0] = web-gw, live group X25519, cert RSA-2048, drift pqc_claimed_not_negotiated (run e3a8fb9f) -->
**Say:** "We scanned 37 files and found 29 quantum-vulnerable uses across 16 assets, each with file and line, and the live probe caught a gateway whose config claims post-quantum but actually negotiates classical X25519."

## 4. Schedule (20 s)

**Command:** switch to the viz tab (2D view, top chart and the "Exposure-years avoided" card).
**On screen:** three panels (Z2030 / Z2032 / Z2035) of remaining exposure-years per week, optimised vs FCFS vs greedy; 7 waves with coloured status markers <!-- results.json: len(waves) = 7 -->.
Avoided by the QpiAI Opt plan:

| scenario | vs FCFS | vs greedy |
|---|---|---|
| Z2030 | 0.173 <!-- avoided.vs_fcfs[0].exposure_years_avoided --> | 0.019 <!-- avoided.vs_greedy[0].exposure_years_avoided --> |
| Z2032 | 0.154 <!-- avoided.vs_fcfs[1].exposure_years_avoided --> | 0.038 <!-- avoided.vs_greedy[1].exposure_years_avoided --> |
| Z2035 | 0.096 <!-- avoided.vs_fcfs[2].exposure_years_avoided --> | 0.058 <!-- avoided.vs_greedy[2].exposure_years_avoided --> |

<!-- solver: exposure.produced_by.solver = "qpiai-opt local"; run_ids 0fe509ea…, cc7eb9a6…; job_ids [null, null]
     (local solves issue no job ID; solver_runs[*].job_id_reason); solver_runs[*].guarantee = global_optimum.
     Totals Z2030: optimised 90.077 vs FCFS 90.250 vs greedy 90.096 exposure-years (exposure.per_scenario[0], baselines.*.per_scenario[0]). -->
**Say:** "QpiAI Opt finds a proven-optimal wave plan that is never worse than first-come-first-served or greedy on the same data; the gain is honest and small, because most exposure is already locked in by long data shelf lives."
*(If asked: hover any number for its run_id, solver and job_id; the job_id is null because local QpiAI Opt solves don't issue one, and the reason is logged.)*

## 5. Handshakes (20 s)

**Command:**
```bash
python -m capture --out-dir "$DEMO" --runs "$DEMO/runs" | grep -E "gate (pq_handshake|pq_auth)"
```
**On screen** (0.8 s <!-- rehearsal timing on the demo laptop, 2026-10-28 -->, real TLS 1.3 handshakes on 127.0.0.1):
```
gate pq_handshake  legacy  FAIL  X25519 is classical ...  [HNDL-exposed: recorded traffic relies on classical key exchange]
gate pq_handshake  hybrid  PASS  X25519MLKEM768 is on the PQ allowlist
gate pq_handshake  pq-auth PASS  X25519MLKEM768 is on the PQ allowlist
gate pq_auth       legacy  FAIL  server authenticates with RSA ...
gate pq_auth       hybrid  FAIL  server authenticates with RSA ...
gate pq_auth       pq-auth PASS  server authenticates with ML-DSA (mldsa65)
```
<!-- results.json: handshake_evidence.sessions = legacy X25519/classical/RSA, hybrid X25519MLKEM768/hybrid-pq/RSA,
     pq-auth X25519MLKEM768/hybrid-pq/ML-DSA (capture run c2f0add7); gates.pq_handshake = FAIL/PASS/PASS;
     gates.pq_auth = FAIL/FAIL/PASS; gates.downgrade: hybrid and pq-auth refuse a classical-only client (PASS).
     Waves: gates.wave_asset_counts = applied 10, not_verified_in_lab 6; gates.forced_rollback.status = rolled_back. -->
**Say:** "These are real TLS 1.3 handshakes: legacy is flagged harvest-now-decrypt-later, hybrid gets ML-KEM key exchange but still signs with RSA, and only the pq-auth service is post-quantum end to end; a classical-only client is refused by the hybrid services, so there is no silent downgrade."

## 6. Ledger tamper (25 s)

Works on a **copy** of the ledger in `$DEMO`; the real `out/ledger.jsonl`, `out/results.json` and verify status are never touched (verifying a copy is not recorded; covered by `tests/test_ledger.py::test_verifying_a_copy_never_touches_recorded_results`).

**Commands** (paste one by one):
```bash
cp out/ledger.jsonl "$DEMO/ledger.jsonl"
python -m ledger verify --ledger "$DEMO/ledger.jsonl"
python -c "import json,sys; p=sys.argv[1]; L=open(p).read().splitlines(); e=json.loads(L[2]); e['type']='detect.run-FORGED'; L[2]=json.dumps(e,sort_keys=True,separators=(',',':')); open(p,'w').write('\n'.join(L)+'\n'); print('edited entry #2 in the COPY')" "$DEMO/ledger.jsonl"
python -m ledger verify --ledger "$DEMO/ledger.jsonl"
```
**On screen:**
```
OK: 52 entries; chain, ML-DSA-65 signatures and payload hashes verified; root e8b64d3a…d7c616 matches results.json
edited entry #2 in the COPY
FAIL at index 2: ML-DSA-65 signature does not verify
```
<!-- results.json: ledger.entry_count = 52, ledger.root = e8b64d3a7cdb5f6d7c5b2c9accf50d9d26c9aa024f83f1916d482cf2e1d7c616,
     ledger.alg = ML-DSA-65 via openssl-cli (OpenSSL 3.6.5); out/ledger.jsonl line 3 = entry #2, type detect.run.
     Rehearsed on 2026-10-28: exit code 1, real files byte-identical afterwards. -->
**Say:** "Every run is signed with ML-DSA-65 into a hash-chained log with a Merkle root; change one field in one entry and verification fails at exactly that entry."

## 7. QAOA (10 s)

**Command:** switch to the viz tab, scroll to "QAOA wave selection: measured cross-check, no quantum advantage".
**On screen:** exact optimum (brute force) objective −0.346154, assets backup and statements <!-- qaoa.exact.objective = -0.34615…; qaoa.exact.assets -->;
feasible fraction local p=3 0.1948 vs random 0.0034, P(optimal set) 0.0156 vs 0.0010 <!-- qaoa.table p=3 local / random .metrics.feasible_fraction, .p_optimal_assets (qaoa run 696c6003) -->;
QCloud rows read "not run: QCloud sampling is opt-in (python -m qaoa --qcloud)" <!-- qaoa.table[*].status_text -->.
**Say:** "QAOA on a simulator is measured against the exact brute-force optimum of a 14-variable wave problem: it finds far more feasible plans than random, and we claim no quantum advantage."
<!-- qaoa.problem.n_variables = 14 -->

## 8. Close (5 s)

**Command:** click **Report** in the viz header (opens `out/report.html`).
**On screen:** the self-contained report, overall PASS, every number tagged with its run_id.
**Say:** "Everything you saw is in one signed, offline report: find it, plan it, verify it, prove it."

---

## If something breaks live

| symptom | do this (≤ 5 s) |
|---|---|
| anything in the terminal fails, hangs or the network is down | `open ~/Desktop/q-shield-atlas-report.html`: the release's offline report (no server, no network), and keep talking through sections 2–7 of it |
| viz tab blank or port busy | `pkill -f "python -m viz"; python -m viz` (a fresh free port), or use the report above |
| 3D view asked for but no WebGL | stay on 2D: the page shows a notice and falls back by design |
| `capture` errors (OpenSSL) | `python -c "from detect.live_probe import openssl_binary; print(openssl_binary())"` to show the path; otherwise use report section 4 |
| tamper shows OK instead of FAIL | the edit did not apply: re-run the `python -c` line, then verify again |

Check the fallback file matches the release: `shasum -a 256 ~/Desktop/q-shield-atlas-report.html`
should print `7c368b97ffed70f9bfea70f92ee578d47c20d2cbe6e76d8da545714574691f36` (release notes).

After the demo: `rm -rf "$DEMO"` (only scratch copies live there).
