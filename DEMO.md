# Q-Shield Atlas: 2-minute live demo runbook (web app)

Pitch flow: problem → detect → schedule → handshakes → ledger tamper → QAOA → close.
Total budget: **120 s**, all clicks in `python -m atlas_web` (terminal steps are only the fallback). Every number
below is from the current `out/results.json` and ledger (the demo workspace); the source of each number is in an
HTML comment next to it (view the raw file to see them).

<!-- Snapshot: ./run_demo.sh on 2026-10-28, results.json generated_at 2026-10-28T19:41:47Z, RESULT: PASS.
     Ledger 60 entries, root 06cd915f32a252f964e1f3240b75049c317a2f410e10e29b219a88f9b770050a, verified
     (results.json: ledger.entry_count, ledger.root, ledger_verification.ok). Plan, handshake and QAOA numbers are
     deterministic; run_ids, ports, transcript hashes, the ledger entry count and root change on every rerun.
     Do not rerun run_demo.sh right before the demo: the web app, report and export all read this snapshot. -->

## Pre-demo checklist (before you walk up)

- [ ] `conda activate pqc`; close other tabs; Do Not Disturb; charger in.
- [ ] Nothing left running: `pgrep -fl "atlas_web|s_server" || echo clear` prints `clear`.
- [ ] Start the app in venue mode: `python -m atlas_web --demo --kiosk --port 8080` (127.0.0.1; `--kiosk` hides sign-out).
- [ ] Sign in once as a **viewer** account (create it beforehand: `python -m atlas_web create-user --role viewer`),
      then go back to `/` so the pitch starts on the landing page. Browser zoom 100 %, window at least 1280×720.
- [ ] Offline fallback ready: `python -m atlas_web export`, then open `atlas_web/dist/index.html` once to check it loads
      (no server, works over file://; the tamper button replays a result recorded at export time, labelled "recorded").

---

## 1. Problem (10 s): landing page `/`

**On screen:** THE LATTICE: the demo inventory, red flickering crystals with red beams (classical crypto,
HNDL exposure); the Q-day buttons 2030 / 2032 / 2035 change the beam heights.
**Click:** Q-day **2032**: the big number reads **0.154** exposure-years avoided vs FCFS <!-- avoided.vs_fcfs[Z2032].exposure_years_avoided -->.
**Say:** "Every RSA and ECC key exchange recorded today can be decrypted once a quantum computer arrives; the question
for a bank is which systems to move first, and how to prove each move worked."

## 2. Detect (20 s): rail key **2** (Detect)

**On screen:** the codebase as a city of columns, one per scanned file; red markers sit at the line of each finding.
Stats: **37** files scanned, **29** quantum-vulnerable findings, **16** assets to migrate, **1** drift case
<!-- detect.files_scanned = 37; detect.summary.vulnerable_findings = 29; detect.inventory.assets = 16; detect.drift_count = 1 (detect run e53c0762) -->.
**Do:** hover a red marker (file:line, rule, family); click the `web-gw` column → its asset page (camera focuses
the crystal): ECC key exchange + RSA certificate, the live probe negotiated classical X25519 although the config
claims PQC (`pqc_claimed_not_negotiated`).
**Say:** "Every finding has a file and line; the live probe caught a gateway whose config claims post-quantum but negotiates classical."

## 3. Schedule (20 s): rail key **3** (Schedule)

**On screen:** the lattice with the week scrubber; stats avoided vs FCFS / vs greedy for the selected scenario.
Z2030: **0.173** vs FCFS, **0.019** vs greedy; Z2035: **0.096** / **0.058**
<!-- avoided.vs_fcfs / vs_greedy exposure_years_avoided for Z2030 and Z2035 -->; **7** weeks to migrate <!-- exposure.makespan_weeks = 7 -->.
**Do:** drag the week scrubber from 0 to 7: crystals turn cyan wave by wave as their stand-ins pass the lab gates;
beams go out. Hover any number: run_id, solver "qpiai-opt local", job id "none" with the logged reason.
**Say:** "QpiAI Opt finds a proven-optimal wave plan (local MILP, global optimum) that is never worse than first-come-first-served
or greedy on the same data; the gain is honest and small, because long data shelf lives lock most exposure in."
<!-- solver_runs[*].solver = qpiai-opt local, termination optimal, guarantee global_optimum; runs eacf9ac6, a06eb61d; job_id null + job_id_reason -->

## 4. Handshakes (20 s): rail key **4** (Handshakes)

**On screen:** one strand per lab service. `legacy`: single amber-red strand, X25519, labelled
"HNDL-exposed: recorded traffic relies on classical key exchange". `hybrid` and `pq-auth`: two strands braided into
X25519MLKEM768; `pq-auth` has the halo (ML-DSA authentication). A classical-only client particle stops at the wall of the
hybrid services (downgrade refused) and passes through on legacy
<!-- handshake_evidence.sessions: legacy X25519/RSA, hybrid X25519MLKEM768/RSA, pq-auth X25519MLKEM768/ML-DSA; gates.downgrade -->.
Below: compatibility grid and wave gates (**10** assets applied, **6** not verified in lab), tested rollback **rolled back**
<!-- gates.wave_asset_counts = applied 10, not_verified_in_lab 6; gates.forced_rollback.status = rolled_back -->.
**Say:** "Real TLS 1.3 handshakes: legacy is harvest-now-decrypt-later exposed, hybrid gets ML-KEM key exchange, only pq-auth is
post-quantum end to end, and a classical-only client is refused, so there is no silent downgrade."

## 5. Ledger tamper (25 s): rail key **5** (Ledger)

**On screen:** the Merkle tower, one leaf per entry (**60**), root on top, verified ✔ <!-- ledger.entry_count = 60; live verification ok -->.
**Click:** **Tamper a copy**. A shard hits leaf #2; that branch cracks red to the root; the panel shows
"#2: ML-DSA-65 signature does not verify", then heals: "Real ledger untouched (hash unchanged)" with the same hash before and after.
**Say:** "Every run is signed with ML-DSA-65 into a hash-chained log with a Merkle root; change one field in one entry and
verification fails at exactly that entry. We edited a copy; the real ledger's hash is unchanged."

## 6. QAOA (15 s): rail key **6** (QAOA)

**On screen:** "measured cross-check, no quantum advantage". Exact optimum (brute force) **−0.346154**, assets backup and
statements, **14** QUBO variables <!-- qaoa.exact.objective; qaoa.exact.assets; qaoa.problem.n_variables (run 3c6c28ad) -->.
Click p=3: feasible fraction **0.1948** vs random **0.0034**, P(optimal set) **0.0156** vs **0.0010**
<!-- qaoa.table p=3 local / random metrics.feasible_fraction, p_optimal_assets -->. QCloud rows read
"not run: QCloud sampling is opt-in (python -m qaoa --qcloud)" <!-- qaoa.table[*].status_text -->.
**Say:** "QAOA on a simulator, measured against the exact optimum of a 14-variable wave problem: far more feasible plans than random,
and we claim no quantum advantage."

## 7. Close (10 s): rail key **1** (Pipeline)

**On screen:** the eleven run_demo.sh stations and the solver record "QpiAI Opt · local MILP · optimal · global optimum".
**Say:** "Operators upload their own repository or point it at endpoints they are authorised to test, and the same eleven steps
run on their data: find it, plan it, verify it, prove it."

---

## If something breaks live

| symptom | do this (≤ 5 s) |
|---|---|
| app tab blank / server gone | `open atlas_web/dist/index.html`: the static export (no server, no network); same click path, tamper shows "recorded" |
| no WebGL on the venue machine | nothing to do: every route shows its 2D content with a notice |
| port busy | `python -m atlas_web --demo --kiosk` (free port) and use the printed URL |
| anything else | `open out/report.html`: the signed, offline report |

After the demo: stop the server with Ctrl+C (it stops any running step and its lab services).
