# Q-Shield Atlas

**Track: Post-Quantum Cryptography · PQC-01**

Q-Shield Atlas finds the RSA, ECC and DH that a cryptographically relevant quantum computer would
break, turns it into a migration plan, and proves each step. A static scanner and live TLS probes
build the inventory with file:line evidence and catch static-vs-live drift. QpiAI Opt schedules
the migration in weekly waves to minimise harvest-now-decrypt-later exposure under several CRQC
arrival scenarios, and the plan is compared with first-come-first-served and greedy baselines on
the same data. Every wave is verified on real TLS 1.3 lab services: hybrid X25519MLKEM768 key
exchange, no silent downgrade, a client compatibility matrix and a tested rollback. Every run is
signed into an ML-DSA-65 hash-chained ledger with a Merkle root, and a QAOA run is measured against
the brute-force optimum as a cross-check, not a claim of advantage. Everything is shown in a 2D
dashboard and a 3D exposure tower that read only `out/results.json`.

> Lab demo · local TLS lab services on 127.0.0.1 · local single-key test ledger without public
> timestamping · simulator-scale QAOA, no quantum advantage claimed · risk, effort and shelf-life
> values are assumptions (`config/assumptions.json`). No key recovery, factoring or decryption is
> performed or claimed anywhere.

## Architecture

```
                 config/assumptions.json   config/lab.json   config/qaoa.json
                            |                     |                 |
 source tree --> detect/ ---+--> out/inventory.json                 |
 (code, configs,  static scan + live probe + drift  |               |
  deps, certs)          |                           v               |
                        |                     schedule/  --(QpiAI Opt MILP, local; --platform opt-in)
                        |                           | out/schedule.json (plan + FCFS/greedy baselines)
                        |               +-----------+-----------+   |
                        |               v                       v   v
 openssl s_server --> capture/ --> gates/ (pq_handshake, pq_auth,  qaoa/ (wave QUBO, exact brute force,
 legacy | hybrid |     handshake    compat matrix, rollback,       local QAOA p=1..3, random baseline;
 pq-auth (127.0.0.1)  evidence      wave runner)                   QCloud --qcloud opt-in)
                        |               |                           |
                        +---------------+------------+--------------+
                                                     v
                         runs/<run_id>/manifest.json (immutable per-run evidence)
                                                     |
                                    ledger/ (ML-DSA-65 signatures, hash chain, RFC 6962 Merkle root)
                                                     |
                         contracts/assemble --> out/results.json (schema-validated)
                                                     |
                                 +-------------------+-------------------+
                                 v                                       v
                         viz/ (2D SVG default, 3D tower)        atlas announce (terminal)
```

Modules exchange data only through the JSON contracts in `contracts/`.

**Stages** (`contracts/stages.json`, one list for `run_demo.sh`, `atlas_web/runner.py`, `GET /api/stages` and the UI):

1. Detect
2. Proof Chain (code/API name `ledger`): `ledger ingest --only detect.run` signs the Detect evidence before anything else runs
3. Plan
4. Handshakes
5. Gates
6. QAOA
7. Seal: ingest every later run, then verify the whole chain
8. Report

The UI's step names are generated from that file (`python -m contracts.stages --write-js`), and a test keeps them in sync.

**Solvers** (`solvers/`, defaults in `config/solvers.json`): `solvers.solve(subproblem, instance, solver)` returns one
`Solution` (assignment, objective, feasibility, runtime, problem size). There are two subproblems:

| Subproblem | What it decides | Default solver | Other solvers |
|---|---|---|---|
| `migration_schedule` | The full multi-week wave plan | `milp` (QpiAI Opt local) | `fcfs`, `greedy` |
| `link_cutover` | Which links cut over to post-quantum key exchange in one change window. A "link" is one asset's TLS endpoint; there is no network-transmission model | `qaoa` (statevector simulator) | `exact`, `hybrid`, `milp` |

- `hybrid`: QAOA samples are repaired classically, and the classical step decides feasibility.
- Unsupported pairs, such as QAOA on the full schedule, raise `solvers.Unsupported` with the reason.

## Data (`data/`)

`python tools/export_csv.py` writes the data as CSV. Column meaning, unit and source are in `data/DATA_DICTIONARY.md`, and
`data/sources.json` holds the SHA-256 of every input and output.

- `data/real_crypto_observations.csv` is **real**. It holds static-scan findings in two public repositories at pinned
  commits (Online Boutique, OpenTelemetry Demo), plus live TLS 1.3 handshakes with `pq.cloudflareresearch.com`
  (X25519MLKEM768) and `www.gnu.org` (X25519, classical).
- `data/SYNTHETIC_mock_bank_assets.csv` is **synthetic**. It is the fictional 16-asset mock-bank inventory the demo
  schedules. The names are invented and this is not real data.
- Risk, effort and shelf-life values are assumptions (`config/assumptions.json`), not data.

## Quickstart (one command)

```bash
conda env create -f environment.yml && conda activate pqc   # Python 3.12 + OpenSSL 3.6.5 (ML-KEM, ML-DSA)
export QPIAI_OPT_API_KEY=...        # free key from https://opt.qpiai.tech/ (or put it in .env.sh, git-ignored)
./run_demo.sh                       # regenerate everything, then open the viz; --no-open to skip the browser
./announce.sh --fast                # terminal launch screen from out/results.json
./report.sh                         # out/report.html: one offline file, signed into the ledger; opens it
python -m atlas site                # showcase site "The Lattice" (site/), read-only, 127.0.0.1
```

`run_demo.sh` runs a preflight first and prints a fix for each failure: Python 3.12, the pinned
packages, OpenSSL >= 3.5 listing X25519MLKEM768 and ML-DSA-65, a free local port, and the API key.
It then generates the ledger key pair if none exists (it never overwrites one) and runs, timing
each step: detect -> schedule -> capture -> gates -> qaoa -> ledger ingest -> ledger verify ->
assemble -> schema validate -> report -> validate. It ends with PASS/FAIL and cleans up every lab `openssl s_server`.
Running it again appends new signed runs and still verifies. With a plain venv instead of conda:
`python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt` and
`PYTHON=.venv/bin/python ./run_demo.sh`; OpenSSL is found via `$QSHIELD_OPENSSL`, then the path
in `config/lab.json`, then next to the interpreter, then `PATH`. A fresh clone generates its own key pair
in git-ignored `keys/` and signs and verifies with it; the committed project key in `ledger/pubkey/`
is left untouched.

## What each module proves, and how to check it

| module | proves | check it |
|---|---|---|
| `detect/` | where RSA/ECC/DH is, with file:line evidence; live handshakes; static-vs-live drift | `python -m detect --lab-probe web-gw=legacy`; `pytest tests/test_detect.py` (exact match with hand-labelled ground truth incl. decoys); `docs/detect_real_repos.md` |
| `schedule/` | a proven-optimal migration plan under capacity and dependencies, never worse than FCFS or greedy on the same data | `python -m schedule --inventory out/inventory.json`; `pytest tests/test_schedule.py tests/test_sensitivity.py` (brute force, random instances, assumption sensitivity) |
| `capture/` | what real TLS 1.3 handshakes negotiate (group, cipher, cert algorithm), with transcript hashes | `python -m capture`; `out/capture.json` validates against `contracts/capture.schema.json` |
| `gates/` | hybrid key exchange (and separately PQ authentication), no silent downgrade, compatibility per client, tested rollback, per-wave evidence | `python -m gates`; `pytest tests/test_gates_waves.py tests/test_capture_gates.py` |
| `ledger/` | every run manifest is signed (ML-DSA-65) and chained; any edit, deletion, reorder, truncation or key swap is detected at its index | `python -m ledger verify`; `python -m ledger proof N`; `pytest tests/test_ledger.py tests/test_merkle.py` |
| `qaoa/` | a measured QAOA cross-check against the exact optimum of a one-week wave QUBO | `python -m qaoa`; `pytest tests/test_qaoa.py tests/test_qaoa_table.py` |
| `viz/` | every displayed number is a value from results.json with its source; nothing invented for runs that did not happen | `python -m viz`; `pytest tests/test_viz.py` (runs the JS data layer under node) |
| `atlas/` | status computed from results.json, the ledger and the last test run; a signed, self-contained report | `./announce.sh` (runs tests) or `./announce.sh --fast`; `./report.sh`; `pytest tests/test_atlas.py tests/test_report.py` |

**Report** (`python -m atlas report`, `./report.sh`, also built by `run_demo.sh`; `--report-open` opens
it): `out/report.html` is one self-contained, offline HTML file (inline CSS/JS, no external URLs,
data rendered in at build time, so it works over `file://`). It covers the summary with computed
PASS/FAIL checks, inventory, migration plan, handshake evidence, waves and rollback, the ledger with
an inclusion proof, QAOA, assumptions and limits, and how to reproduce. Every number is taken from
results.json and tagged with its run_id/job_id; missing data shows "not yet run". The footer holds
the file's SHA-256 computed with that field set to 64 zeros; the exact file is copied to
`runs/<run_id>/report.html`, signed into the ledger (type `report.html`), and the ledger is verified.
Print → Save as PDF gives a clean document (print CSS expands collapsed sections).

Numbers are deliberately not quoted in this README: they live in `out/results.json`, each one
traceable to a run under `runs/` and a signed ledger entry. `./announce.sh` prints them with sources.

## Showcase site (`site/`, in progress)

`python -m atlas site` serves "The Lattice", a scroll-driven WebGL story built from the current
`out/results.json` and ledger. (The brief named it `python -m site`, but that name is Python's
standard-library `site` module, so the backend lives in `atlas/site_server.py`.) The server is
read-only and stdlib-only: it serves `site/`, the hash-checked three.js from `viz/vendor/`, the 2D
viz as the no-WebGL fallback, and `/api/results`, `/api/ledger` (with an in-memory, unrecorded
verification), `/api/handshakes` and `/api/events` (SSE on file change). It binds 127.0.0.1 on a free
port; `keys/`, `.env.sh`, `runs/`, the ledger file and source files return 404. Chapters 1–4
(harvest, detect, schedule, handshake) are built; ledger, QAOA, close, the tamper endpoint and the
static export are next. Every number comes from the API with a provenance tooltip; `?debug` shows fps
and draw calls; `prefers-reduced-motion` gives a static camera.

## Web app (`atlas_web/`)

`python -m atlas_web` serves a login-protected, routed web app on 127.0.0.1 that drives the whole pipeline
through the existing module CLIs (one subprocess per step, with workspace path flags) and shows the results in
THE LATTICE, one persistent three.js world (vendored, hash-checked; 2D fallback without WebGL).

```bash
python -m atlas_web create-user --role admin     # no default user; password via getpass
python -m atlas_web                              # 127.0.0.1, free port, opens the browser
python -m atlas_web --demo --kiosk --port 8080   # venue mode: landing on the demo snapshot, no sign-out
python -m atlas_web export                       # static read-only snapshot in atlas_web/dist/ (works over file://)
```

- **Workspaces:** `demo` is the repo's `out/` + `runs/`, read-only. Others live in git-ignored
  `atlas_web/data/workspaces/<id>/{src,out,runs,config,keys}` with their own ML-DSA-65 key; the repo's `out/`,
  `runs/` and `keys/` are never written (tested). All workspaces share `runs/platform_jobs.log`, so the paid-run
  daily cap stays global.
- **Real data:** .zip upload (absolute paths, `..`, symlinks and zip bombs rejected; nothing executed), shallow
  clone of a public https repository, an `atlas-service.json` editor, live TLS probes behind an
  "I own or am authorised to test these endpoints" confirmation that is stored with the run, an assumptions editor
  and calibration ("calibrated from your measurements": medians of recorded engineer-days, never applied
  automatically; applying re-plans and signs a `calibration.apply` entry with `python -m ledger append`).
- **Real repositories:** `python tools/seed_real_workspaces.py --confirm` builds the REAL REPO workspaces from the
  repos pinned in `detect/real_repos.json` (Online Boutique, OpenTelemetry Demo) through the same API: clone at the
  pinned commit, "Suggest manifests" (kind from evidence, data class `internal_ops`, dependencies from compose
  `depends_on` / k8s `<service>:<port>` references; every field marked "suggested — review" with its basis), operator
  confirmation (runs are refused until then), then the full pipeline. An inventory with no RSA/ECC/DH gives an honest
  empty plan ("nothing to migrate", no solver run) instead of an error. Asset pages show the manual-review notes from
  `docs/detect_real_repos.md`.
- **Public PQ reference endpoints:** a probe preset with `pq.cloudflareresearch.com:443` (hybrid X25519MLKEM768) and
  `www.gnu.org:443` (refused an X25519MLKEM768-only offer when verified on 2026-10-29, so classical): one standard TLS
  handshake each, no scanning; shown in drift, as live strands on Handshakes, and on asset pages.
- **Roles:** viewer (read), operator (run, upload, calibrate), admin (users; paid QpiAI runs, which stay disabled in
  `config/atlas_web.json` until the account issues are fixed). scrypt passwords, hashed session tokens, CSRF
  double-submit, login rate limit.
- **Honesty:** every number comes from results.json or the ledger with its run_id, solver, job_id (or the reason
  there is none) and ledger index on hover/focus; missing data reads "not yet run". Positions in the 3D world are
  layout; colours, beams, heights and pulses map to recorded fields (status, exposure-years, week, findings).
  The tamper demo verifies an edited temporary copy; the real ledger's hash is checked unchanged.
- **Checks:** `pytest` (API, auth, access matrix, zip safety, full pipeline and end-to-end runs in temp
  workspaces, crash recovery), `node --test atlas_web/jstests/*.test.mjs`, `python tools/route_check.py`
  (every route × 3 sizes × 4 roles in headless Chrome, plus the static export over file://, zero errors) and
  `python tools/bench_api.py` (read API p95).

## Assumptions and limits

- **Assumptions, not measurements:** shelf life and risk weight per data class, effort per asset
  kind, weekly capacity, start year, CRQC scenario years (2030, 2032, 2035) and weights
  (`config/assumptions.json`). Sensitivity runs scale shelf life, risk and effort by 0.8 and 1.2.
  Each asset must fit in one week of capacity.
- **Exposure model:** Mosca's inequality, linear in completion time. With shelf lives long relative
  to time-to-CRQC most exposure is structural, so the plan can only reduce the part that depends on
  finishing earlier; `avoided` reports exactly that.
- **Chart semantics:** the viz plots unweighted exposure-years, while the optimiser minimises the
  risk-weighted, scenario-weighted total, so in some weeks its unweighted curve sits above a baseline.
- **Lab, not production:** TLS services are local `openssl s_server` processes on 127.0.0.1. The
  legacy and hybrid lab certificates are RSA-2048; only `pq-auth` uses an ML-DSA-65 certificate.
  Wave verification uses one lab stand-in per asset kind (edge, app, data); kinds with no TLS stand-in
  (root CA, HSM, VPN, batch SFTP) are reported `not_verified_in_lab`, never passed. "applied" means the
  stand-in passed the gates, not that the real system was migrated.
- **Static scan:** line-based rules, no data-flow analysis; hand-made ground truth; crypto configured
  outside the repo (cloud load balancers, mesh defaults) is only visible to the live probe. Known
  misses and fixed false positives on real repos: `docs/detect_real_repos.md`.
- **Ledger:** a local test ledger with one signing key and no public timestamping or transparency
  log; its anchor in results.json is only as trustworthy as wherever results.json is published.
- **QAOA:** simulator scale (at most 16 variables, `config/qaoa.json`), small enough for brute force; no quantum advantage
  claimed. The approximation ratio saturates at this size, so feasible fraction, energy ratio and
  P(optimal set) are the informative comparisons.
- **QpiAI platform status:** QpiAI Opt platform MILP submissions were rejected ("no active storage
  quota found for organization") and QCloud job creation was rejected ("an active subscription is
  required to run jobs"); no platform job was created. Scheduling uses free local QpiAI Opt solves
  (`job_id: null` with a reason, run_id and input/output hashes). QAOA circuits are sampled on two free local
  backends: our numpy statevector and the QpiAI SDK's in-process simulator (`qpiai-quantum` 0.3.0
  `StatevectorSimulator`, "QpiAI-QSV-Local"; `python -m qaoa --qpiai-local`, default in run_demo.sh): no network,
  no credits, `job_id: null` with the reason "local SDK simulation issues no job ID", SDK version, run_id and
  input/output hashes, compared with the numpy rows by z-score.
  Rows for runs that did not happen show their status text, never numbers.
- **Toolchain:** OpenSSL >= 3.5 is required (ML-KEM groups, ML-DSA); the system LibreSSL and older
  OpenSSL builds do not work.

## Opt-in paid runs

Default runs never submit QpiAI Opt or QCloud jobs (`QSHIELD_FORBID_PLATFORM=1`; tests force it).

```bash
./run_demo.sh --platform          # 2 QpiAI Opt platform jobs (main plan), same input also solved locally
./run_demo.sh --qcloud            # 3 QCloud jobs on QpiAI-QSV-Simulator only (one final circuit per p)
./run_demo.sh --qcloud --allow-more   # past the 10-submissions-per-UTC-day cap
```

Each submission is announced ("Submitting N ... jobs"), logged to `runs/platform_jobs.log` and the
run directory, refused past the daily cap, and stopped after the first failure; real hardware
(`QpiAI-Indus-1`) is refused. Platform and local results are reported side by side, never merged.

## Version pins

- Python 3.12; `requirements.txt` pins the direct imports: cryptography 50.0.2, jsonschema 4.26.0,
  numpy 2.5.4, psutil 7.2.2, pytest 9.1.1, **qpiai-opt 0.0.9**, **qpiai-quantum 0.3.0**, rich 15.0.0,
  scipy 1.18.1. `requirements-lock.txt` is the full environment snapshot; `environment.yml` adds
  conda-forge `openssl=3.6.5`.
- OpenSSL: `config/lab.json` `openssl` records the binary path and version used
  (OpenSSL 3.6.5, conda-forge `h55eecbc_0`) and the required X25519MLKEM768 / ML-DSA-65 support.
- three.js 0.170.0 vendored in `viz/vendor/` with SHA-256s in `viz/vendor/MANIFEST.json` (below).
- QpiAI API surface actually used: `docs/qpiai_api_notes.md`.

## Rerunning single modules

```bash
python -m detect --lab-probe web-gw=legacy  # or --probe SERVICE=HOST:PORT
python -m schedule --inventory out/inventory.json [--platform]
python -m capture && python -m gates
python -m qaoa [--qpiai-local] [--qcloud]
python -m ledger ingest && python -m ledger verify   # also: python -m ledger proof N, keygen
python -m contracts.assemble && python -m contracts validate results out/results.json
python -m viz [--no-browser]
pytest                                      # QpiAI solver tests skip without QPIAI_OPT_API_KEY
```

Every step can target a separate workspace instead of the repo's `out/`, `runs/` and `keys/` (defaults
unchanged): `--out-dir`/`--runs` on all modules, `contracts.assemble --out-dir`, `ledger --root DIR`
(the directory `payload_ref`/`ledger_ref` are relative to) `--keys-dir DIR`, `atlas report --out-dir
--runs --root --keys-dir`, `detect --probe-timeout S` (a timeout is recorded as `probe_failed`), and
`schedule`/`qaoa --platform-log FILE` so several workspaces share one daily-cap log.

# Module details

## Detection (`detect/`)

- **Static scan** (`detect/static_scan.py`, rules in `detect/rules.py`): code (Python, Go, Java/Kotlin,
  JS/TS, C#), configs (nginx/TLS ciphers and groups, OpenSSL, SSH, IPsec, Kafka/Postgres, JWT algs),
  dependency manifests, and certificates (parsed for key type and size). Each finding has file:line,
  rule, family (RSA/ECC/DH/DSA, PQC for hybrid/ML-KEM, UNKNOWN for TLS on library defaults) and use
  (kex/sig). Private-key bodies are never read into output. A tree SHA-256 ties each scan to the
  exact files seen. Nothing in a scanned tree is executed.
- **Inventory** (`detect/inventory.py`): services are directories with an owner-declared
  `atlas-service.json` (name, kind, data class, dependencies: facts a scanner cannot infer).
  Services with RSA/ECC/DH/DSA findings become migration assets carrying their evidence; others
  are listed as not vulnerable. The output is the schedule's inventory format.
- **Live probe** (`detect/live_probe.py`): `openssl s_client` from the `pqc` env (OpenSSL 3.6.5)
  offers `X25519MLKEM768:X25519:prime256v1` and records the negotiated group, certificate key and
  the transcript hash (transcript saved under `runs/<run_id>/`).
- **Drift** (`detect/drift.py`): config claims a hybrid group but the live handshake is classical;
  live crypto with no static evidence; live PQC not in config; probe failure.

Fixtures: `detect/fixtures/sample_services` (fake multi-language services with decoys and
hand-written ground truth in `expected.json`) and `detect/fixtures/mock_bank` (17 fictional
services generated by `build_mock_bank.py`; scanning it reproduces the 16-asset demo inventory,
and `web-gw` is the drift case). Real repos: `python -m detect.real_repos` scans two pinned public
microservice repos; the manual review of every finding is in `docs/detect_real_repos.md`.

Limits: regex/line-based static rules (no data-flow analysis); ground truth is small and hand-made;
crypto configured outside the repo (cloud LB policies, mesh defaults) is only visible to the probe.

## Handshake evidence (`capture/`) and the PQ handshake gate (`gates/pq_handshake.py`)

Requires OpenSSL >= 3.5 with ML-KEM: the `pqc` env pins conda-forge `openssl 3.6.5 h55eecbc_0`.
(The system LibreSSL 3.3.6 and the base env's OpenSSL 3.0.18 have no ML-KEM.) Tests that need
ML-KEM skip with that reason instead of passing.

- `capture/services.py` starts two real TLS 1.3 services with `openssl s_server`, each with a fresh
  self-signed RSA-2048 certificate in a temp dir, bound to 127.0.0.1 on a free port:
  **legacy** (`-groups X25519`, classical) and **hybrid** (`-groups X25519MLKEM768`).
  Processes are terminated (then killed if needed) on exit, including on errors.
- `capture/handshake.py` connects with `openssl s_client -groups <list> -brief -msg` and records the
  negotiated group, cipher, protocol and certificate key family (from the TLS signature type), plus
  the raw transcript (saved under `runs/<run_id>/`) and its SHA-256. Each service is probed by a
  modern client (`X25519MLKEM768:X25519`) and by a classical-only client (`X25519:prime256v1`).
  `out/capture.json` follows `contracts/capture.schema.json`; failed handshakes go to `refused_attempts`.
- `gates/pq_handshake.py` reads capture.json only. **pq_handshake** passes only if the negotiated group
  is on the allowlist in `config/lab.json`. **downgrade** passes only if the classical-only client was
  refused; with no recorded attempt it reports `NOT_RUN`, not a pass.
- Sessions that negotiated a classical group are labelled
  *"HNDL-exposed: recorded traffic relies on classical key exchange"* in `results.json`
  (`handshake_evidence`). That is a statement about the key exchange, not a demonstrated break:
  no traffic is decrypted and no decryption is claimed.

A third service, **pq-auth** (strict mode, ML-DSA-65 certificate), shows post-quantum authentication:
the `pq_auth` gate reports the certificate signature algorithm separately from the key exchange.
Measured: legacy and hybrid authenticate with RSA (`rsa_pss_rsae_sha256`, pq_auth FAIL); pq-auth
authenticates with `mldsa65` (pq_auth PASS). Classical authentication is not an HNDL exposure (a past
session cannot be retroactively impersonated) but must be replaced before a CRQC exists. `-msg` adds the hex of every
handshake message (including the ClientHello/ServerHello randoms), so each session's transcript hash
is unique. Key material is never logged: no `-keylogfile`, and `SSLKEYLOGFILE` is stripped from the
subprocess environment (tested).

## Deployment modes, compatibility, rollback and waves (`gates/`)

Modes (`config/lab.json`): **legacy** = X25519, TLS 1.2+; **transition** = X25519MLKEM768:X25519,
TLS 1.2+ (hybrid preferred, classical still allowed); **strict** = X25519MLKEM768, **TLS 1.3 only**.
Strict must be TLS 1.3-only: measured with OpenSSL 3.6.5, a strict-groups server that still allowed
TLS 1.2 let a TLS 1.2 client in on classical finite-field DH (`Peer Temp Key: DH, 2048 bits`),
because ML-KEM groups exist only in TLS 1.3.

- `gates/compat.py`: matrix of modes x clients (pq-capable, classical-only, TLS1.2-only). Expected
  outcomes come from the `compat_policy` table in config. Code adds two rules on top: a pq-capable
  client in a mode offering a PQ group must get one (no silent downgrade), and any classical
  connection is `HNDL-exposed`, never `PASS`. Cells: PASS | HNDL-exposed | FAIL; any FAIL fails the gate.
- `gates/rollback.py`: snapshot the service config file + SHA-256, apply the mode, restart, run
  pq_handshake + compat. On failure: restore, verify the restored file's SHA-256 equals the snapshot,
  restart, run a classical-client health-check handshake. Status: `applied` (all gates passed),
  `rolled_back`, or `rollback_failed` (hash mismatch, restart failure or failed health check).
- `gates/wave_runner.py`: reads waves from `out/schedule.json`; for each wave moves the lab stand-ins
  its assets map to (by asset kind: edge, app, data; at most 4 `s_server` processes) to the target
  mode with rollback protection. Evidence per wave (gate results, transcript hashes, config hashes,
  timestamps, run_id) goes to `runs/<run_id>/` and `results.json` `waves[].evidence`; the schema
  requires evidence for any non-planned wave status.
- Statuses: `applied` | `rolled_back` | `rollback_failed` | `not_verified_in_lab` (asset kinds with no
  TLS stand-in: root CA, HSM, VPN, batch SFTP) | `partially_verified` (wave mixing both).

Limits: one lab stand-in represents every asset of its kind, so `applied` means the stand-in
passed the gates in that mode, not that the real system was migrated. Lab certificates stay RSA-2048.

## Signed evidence ledger (`ledger/`)

- **Backend:** ML-DSA-65 via the OpenSSL 3.6.5 CLI (`genpkey -algorithm ML-DSA-65`,
  `pkeyutl -sign/-verify -rawin`). Detection order was (a) OpenSSL CLI, (b) `cryptography` 50.0.2
  (`mldsa.MLDSA65PrivateKey`), (c) liboqs-python 0.16; all three passed a sign / verify /
  tampered-message / tampered-signature round trip, so (a) is used. A self-test runs before use and
  there is no fallback to RSA, ECDSA or Ed25519. Tests cross-verify every OpenSSL signature with
  `cryptography` as an independent ML-DSA-65 implementation.
- **Keys:** `keys/ledger_mldsa65.key` (git-ignored, mode 0600, never printed). Committed: the public
  key `ledger/pubkey/ledger_mldsa65.pub.pem` and its fingerprint (SHA-256 of the DER
  SubjectPublicKeyInfo) in `ledger_mldsa65.pub.sha256`. To sign on a new machine, run
  `python -m ledger keygen`: it refuses to overwrite an existing key and writes the new key pair
  and fingerprint to git-ignored `keys/`, which signing and verification then prefer over the
  committed key. To sign as the project, copy the private key out of band. Verifying the
  project's ledger needs only the committed public key.
- **Log** (`ledger/log.py`): append-only JSONL under an exclusive file lock. Entry =
  `{index, type, payload_hash, payload_ref, prev_hash, ts, alg, backend, pubkey_fp, sig_mldsa}`.
  Canonical JSON (sorted keys, `(",", ":")`, UTF-8); the signature covers the entry without
  `sig_mldsa`; `prev_hash` is SHA-256 of the previous entry including its signature (genesis: 64 zeros).
- **Merkle** (`ledger/merkle.py`): RFC 6962 (leaf `0x00`, node `0x01`, split at the largest power of
  two, i.e. odd nodes promoted); inclusion proofs verified with the RFC 9162 algorithm. Checked
  against the Certificate Transparency reference roots and an independent promote-odd build.
- **Ingest:** signs the immutable per-run payloads under `runs/<run_id>/` (schedule solver runs with
  job_id/problem_id/solver and input/output hashes, detect, capture with transcript hashes, gates,
  wave runner with per-wave status and config hashes). Re-ingesting the same payload is a no-op.
  Root, entry count, public-key fingerprint, algorithm and backend are anchored in `results.json`.
- **Verify:** per entry: schema, index, chain, key fingerprint, signature, payload re-hash; then the
  anchored root. Reports the first failing index and reason. Tests cover a one-byte payload edit,
  an edited field, a corrupted signature, a deleted middle entry, reordered entries, a truncated
  tail (root no longer matches the anchor), a different public key, and an entry re-signed with
  another key.

Limits: a local test ledger with one signing key; no external timestamping or transparency log, so
the anchor in `results.json` is only as trustworthy as wherever results.json is published.

## QAOA cross-check (`qaoa/`)

> **QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage
> claimed; the problem is small enough for brute force.**

- **QUBO** (`qaoa/qubo.py`): one week of the latest schedule. Candidates are assets not migrated
  before that week; at most 10 assets + ceil(log2(C+1)) slack bits, at most 16 variables. The candidate set is
  shrunk by value per effort day together with each asset's unmet dependencies, and every drop is logged.
  Value a_i is the scenario-weighted exposure-years avoided by migrating in that week rather than one week
  later (same Mosca data as the MILP); objective minimises -sum r_i a_i x_i. Capacity uses binary slack with
  penalty A(sum w_i x_i + s - C)^2; dependency i needs j uses B x_i (1 - x_j); A = B = 1 + sum|c_i|, so every
  infeasible state costs more than the empty selection. The exact optimum is brute force over all subsets,
  and tests check the QUBO minimum equals it.
- **Bit order:** variable k = qubit k = bit k of the basis index; counts strings have qubit 0 rightmost.
  Verified against the QpiAI SDK's in-process simulator (gate conventions too: the QCloud circuit
  reproduces the numpy QAOA state with overlap 1.0).
- **Local QAOA** (`qaoa/local_sim.py`): numpy statevector, p = 1, 2, 3, angles from scipy COBYLA on the
  expected energy, 5 seeded restarts; samples drawn with a fixed seed. Baseline: the same number of
  uniformly random bitstrings.
- **QpiAI SDK local simulator** (`qaoa/qpiai_local.py`, `python -m qaoa --qpiai-local`, default in `run_demo.sh`):
  the same final circuit per p (2048 shots, seeded) run on `qpiai_quantum.simulator.StatevectorSimulator` in-process;
  free, offline, no platform guard needed. Rows `qpiai_local` sit next to the numpy rows in `qaoa.table` with
  z-scores against them; tests check that the SDK's exact statevector equals the numpy QAOA state.
- **QCloud** (`qaoa/qcloud_run.py`, opt-in `python -m qaoa --qcloud`): submits only the final circuit per p
  (2048 shots, at most 3 jobs) to `QpiAI-QSV-Simulator` (usage rate 1; QPU `QpiAI-Indus-1` refused),
  through the same guard as the scheduler (announce, log, 10 jobs/UTC day shared, refused under pytest).
  Local and QCloud statistics are compared with z-scores; large differences are reported, both kept.
  **Current status: no QCloud results.** Attempts on 2026-10-28 were rejected before any job was
  created: first `Experiment 'qshield-qaoa-crosscheck' not found` (the SDK cannot create experiments;
  now uses the existing `Default Experiment`, checked read-only before submitting), then
  `Failed to create job: an active subscription is required to run jobs`. The account shows 0 QCloud
  jobs. All QAOA numbers so far come from the local numpy simulator and the random baseline.
- **Metrics** (`qaoa/metrics.py`): feasible fraction; best feasible objective; approximation ratio =
  best_feasible / exact_optimum (both <= 0, so 1 = optimum found); energy ratio
  (E_max - mean E)/(E_max - E_min); probability of the exact optimal bitstring and of the optimal asset set.
- **Display table** (`results.json` `qaoa.table`, built by `qaoa/table.py` at assembly): one row per
  (p, local/QCloud) plus the random baseline. Rows that did not run have `metrics: null` and a
  `status_text` derived from the logged error and the ledger entry, e.g.
  `skipped: no QCloud subscription (attempt logged, ledger #7)`; never blanks or zeros (the schema
  enforces this). A later successful `--qcloud` run yields `ok` rows with metrics and job IDs through
  the same path, so viewers need no code change.
- **Reading the results:** at this size the approximation ratio saturates at 1 even for random sampling
  (2048 shots over 2^14 states hit the optimum by chance), so feasible fraction, energy ratio and
  P(optimal set) are the informative comparisons. The QAOA run is signed into the ledger (`qaoa.run`).

## Visualisation (`viz/`)

Vanilla JS + SVG, no framework, no build step, works offline. `python -m viz` serves only `viz/` and
`out/results.json` on 127.0.0.1 (free port); every other path (including `keys/`) returns 404.

- **Data:** reads only `out/results.json`, including the ledger verification status. `viz/data.js` turns
  it into a display model; every number is a value present in results.json and carries its source
  (run_id, solver/backend, job_id, timestamp), shown on hover, focus or tap. Rows that did not run show
  their `status_text`; absent sections or fields show "not yet run", never 0. A later successful QCloud
  run appears with no code change.
- **2D (default, no WebGL):** remaining exposure-years per week for the optimised plan vs FCFS vs greedy,
  one panel per CRQC scenario, with wave markers coloured by lab-gate status; cards for exposure-years
  avoided, the ledger (short root, entry count, verified ✔/✖, only for the anchored root), the TLS handshake
  table (key exchange and authentication per lab service) and the QAOA table ("measured cross-check, no
  quantum advantage"). The chart shows unweighted exposure-years while the optimiser minimises the
  risk-weighted, scenario-weighted total, so its curve can sit above a baseline in some weeks; the page says so.
- **3D (opt-in, needs WebGL):** the exposure tower (one floor per week, floor height = remaining
  exposure-years), a week slider and scenario picker, and red HNDL beams on every service still on classical
  key exchange; a beam switches off only when that service's pq_handshake gate PASSes in results.json. If
  WebGL is missing or fails, the page stays on 2D with a visible notice. `?view=3d&week=N` opens it directly.
- **Always-visible banner:** "Lab demo · local test ledger · simulator-scale QAOA · risk, effort and
  shelf-life values are assumptions (config/assumptions.json)".
- **Vendored three.js** (no CDN), recorded in `viz/vendor/MANIFEST.json` and checked by tests:
  `three-0.170.0.module.min.js` (from the npm tarball `three@0.170.0`, `build/three.module.min.js`)
  SHA-256 `08fd7545d13d2c7fb65ab691530a802dafefd638596501854f267d0fb13c39e7`; MIT licence file
  `three-LICENSE.txt` SHA-256 `4c40a1ef62450b857c3b2aaf294936304cd552d965fbcd9d32d4c5bcf4ba4454`.
  The tarball matched the registry's sha512 integrity when downloaded.
- **Tests** run the real `viz/data.js` under node (skipped with a reason if node is absent) against a
  snapshot of a logged `results.json` (`tests/fixtures/results_sample.json`). No playwright check: it is not
  installed; the no-WebGL fallback was checked with headless Chrome.

## Scheduling model (`schedule/`)

Per asset i: shelf life X_i (years), effort w_i (engineer-days), risk weight r_i, dependencies.
Each asset is assigned to one week k (wave); completion time t_i = k/52 years after `start_year`.
For each CRQC scenario year Z (default 2030, 2032, 2035), exposure is
e_i = max(0, X_i + t_i − (Z − start_year)) years (Mosca's inequality).

- Constraints: each asset migrates exactly once; weekly effort ≤ capacity; a dependency
  migrates no later than its dependents.
- `objective: "expected"` minimises the scenario-weighted sum of r_i·e_i;
  `"robust"` minimises the worst case across scenarios.
- Solved lexicographically with QpiAI Opt (local MILP, `mip_rel_gap=0`): primary objective,
  then (robust only) the expected objective, then a tie-break Σ r_i·t_i that pulls high-risk
  assets earlier when exposure is already zero. Each stage fixes the previous optimum.
  A stage that does not report `termination=optimal` aborts the run.
- Baselines on the same data: **FCFS** (inventory/discovery order) and **greedy**
  (highest r_i/w_i first). Both are list schedulers that respect dependencies and capacity.
- Every plan, including the MILP's, is re-scored by an independent evaluator
  (`schedule/problem.py:evaluate`) and re-checked for feasibility; solver objectives are not trusted.
- The MILP horizon is extended to cover both baseline plans, so both baselines are feasible MILP
  solutions and a proven optimum cannot be worse. Tests check this on the demo data, random
  instances, and against brute-force enumeration on a small instance.

### Which solver produced each number

Every plan in `results.json` (`exposure`, `baselines.*`) carries `produced_by`
(`solver`, `run_ids`, `job_ids`), and every entry in `solver_runs` has a `solver` label:
`qpiai-opt platform`, `qpiai-opt local`, `qpiai-opt local (fallback: platform submission failed)`
or `qpiai-opt local (fallback: platform skipped after an earlier failure in this run)`.
Sensitivity rows always come from local solves and say so in `produced_by`.

### Platform mode (opt-in, guarded)

- Default is local. Only `python -m schedule --platform` submits paid platform jobs: one per
  main-plan MILP stage (2 for the `expected` objective). Sensitivity, pytest and `run_demo.sh`
  never submit (`QSHIELD_FORBID_PLATFORM=1` makes the guard refuse).
- Before each submission it prints `Submitting N QpiAI jobs`, writes that line to
  `runs/<run_id>/platform_submit.log`, and appends to `runs/platform_jobs.log`.
- At most 10 submissions per UTC day (attempts count, including failed ones); `--allow-more` overrides.
- Each stage is also solved locally on the identical input; `comparison` records both objectives,
  their difference and `match`. A mismatch is printed and kept, not merged.
- If a submission fails, that stage uses the local result labelled as a fallback with the error
  in `fallback_reason`, and the run stops submitting for its remaining stages.

**Current status:** platform submissions are rejected by the QpiAI Opt server with
`APIError: no active storage quota found for organization` (first attempt 2026-10-28). The
account had 0 problems and 0 jobs afterwards, so nothing was created. Until the account has a
storage quota, all scheduling numbers come from local solves and are labelled as such.

### Solver job IDs: documented fallback

QpiAI Opt **local** solves (`mode="local"`, free) do not issue a platform job ID. Each solver
stage is therefore logged with `job_id: null` and a `job_id_reason` string, plus:
our own `run_id` (UUID4), a UTC timestamp, SHA-256 of the exact inputs (problem data, stage,
fixed objective bounds and the LP text) and SHA-256 of the full solver output.
Files: `runs/<run_id>/{inputs.json, solver_output.json, manifest.json}`.
The schema rejects a null `job_id` without a reason. Platform mode (which issues job IDs but can
consume credits) is not used for scheduling.

The local QpiAI Opt MILP runtime reports HiGHS status strings, i.e. it is HiGHS-based.

## Contracts (`contracts/`)

- `capture.schema.json`: established TLS sessions (service_id, negotiated_group, cipher, protocol,
  cert_alg, transcript_sha256, timestamp) and refused handshake attempts. No payloads.
- `results.schema.json`: assets, waves, status, exposure per scenario, baselines, avoided,
  solver runs, sensitivity, and module sections (detect, handshake_evidence, gates, qaoa, ledger, ledger_root, ledger_verification).
- `ledger_entry.schema.json`: `{index, type, payload_hash, payload_ref, prev_hash, ts, alg, backend, pubkey_fp, sig_mldsa}`.
