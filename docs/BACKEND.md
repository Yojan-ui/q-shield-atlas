# Backend: atlas_web server

Detail moved from the README. Short version: [README › Backend](../README.md#backend-atlas_web-server--pipeline-modules). API routes: [API.md](API.md).


### Running the UI

```bash
conda activate pqc && source .env.sh && python -m atlas_web --port 8000   # then open http://127.0.0.1:8000/
python -m atlas_web create-user --role admin                               # first time only (no default user)
```

The pipeline is shown in the order the backend runs it, and each step lights only from its own run events:
**1 Detect** (findings → systems · drift alerts) → **2 Proof chain opened** (the existing chain is verified, then the
Detect evidence is signed) → **3 Plan** (QpiAI Opt MILP vs FCFS / greedy) → **4 Handshake gates** → **5 Wave selection**
(QAOA on a simulator vs the exact answer) → **6 Proof verified** (every result signed, the chain re-verified) → **7 Review**.
Run pipeline on any non-demo workspace opens the guided 3D run with its live log; Replay last run replays the latest
recorded run. Scan your own repo (landing or `/settings/new-workspace`) clones a public GitHub repository, suggests
service manifests, and after you confirm them on Detect the run starts from the Pipeline page. The demo workspace is a
read-only snapshot. Press P on any workspace for presenter mode.
Checks: `python tools/ui_check.py` (every page, 3 sizes: console, failed requests, overlapping / clipped text,
overflow) and `python tools/browser_flow.py` (GitHub-URL flow + live runs in a real browser).

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
- **Pages:** the route rail follows the stage order. Keys 1–9: Pipeline, Detect, Proof Chain, Plan, Handshakes, QAOA, Benchmark, Review, Migration.
  - **Pipeline** opens with "At a glance": one card per stage, each with a plain name, one status (Done / Running /
    Failed / Not run), the key number and a "what this means" line.
  - Every page footer carries the colour legend. Every chart has a one-line "How to read this" caption.
  - **Detect** opens with a 3D dependency graph of the inventory: one node per system (`results.assets` plus
    `inventory.not_vulnerable`), one line per declared `depends_on`. Red = RSA/ECC/DH/DSA found; amber = needs a live
    probe; cyan = PQC/hybrid key exchange (a classical certificate signature alone is noted in the side panel);
    grey = nothing vulnerable. Node size is the risk weight (an assumption); a white ring marks recorded
    static-vs-live drift. Click a node for its file:line evidence. Flat 2D graph on request and without WebGL.
  - **Plan** shows remaining exposure-years per week for the optimised plan, FCFS and greedy (`remaining_by_week`,
    unweighted, so lines can cross) and a large "Exposure-years avoided vs FCFS" from `avoided`.
  - **Proof Chain** shows the ledger as linked blocks (green when the live check verified). The one-click tamper
    test edits a temporary copy server-side and verifies it; blocks turn red from the failing index, then the page
    shows the real ledger's SHA-256 unchanged.
  - **Plan** also shows the time estimate: the MILP makespan, plus a capacity lower bound of total assumed effort ÷ weekly
    capacity. You can set a deadline in weeks, and the page flags clearly when the estimate exceeds it. The deadline
    is saved per workspace for operators; otherwise it is kept in this browser only.
  - **Benchmark** (`python -m bench`, or the button) solves the same link cutover instances (6–16 QUBO variables)
    with exact, QpiAI Opt MILP, random sampling, QAOA p=1–3 (simulator) and hybrid. It shows one table and a
    log-scale runtime chart, and states its limits.
    - The hardware row says "not run": the QCloud subscription is blocked, and the project never uses QpiAI-Indus-1.
    - At this size random sampling also finds the optimum. No advantage is claimed.
  - **Review** lists the latest run's plan, waves, QAOA run and benchmark as items awaiting review. Operators
    approve or reject each one with a required reason. Each decision is signed into the Proof Chain as
    `review.decision` and bound to the item's run_id and evidence SHA-256, and the chain is then re-verified.
  - **Migration (Move)** is sender vs receiver: a replay of the recorded lab handshakes, packet by packet.
    - Each packet is one message of the recorded `openssl s_client -msg` transcript (`runs/<run_id>/transcript_*.txt`,
      used only when its SHA-256 matches `capture.json`), as wide as its recorded byte length; key shares are drawn
      inside their hello. API: `GET /api/workspaces/<ws>/move`.
    - Lanes: before (same client, classical X25519 server, HNDL-exposed), after (hybrid X25519MLKEM768), and the
      recorded classical-only attempt (refused / accepted / "not run"). RSA vs ML-DSA-65 server authentication sizes
      from the recorded Certificate and CertificateVerify.
    - The week slider walks the logged plan; each wave shows its recorded lab gate results ("not run in this wave"
      where a gate did not run). "Verified in lab" is the strongest state, for lab stand-ins only. Bank endpoints are
      "observed" (one recorded handshake) and "planned", never applied.
    - **Run fresh handshake now** (operators; `fresh_handshake.enabled` in `config/atlas_web.json`): runs the lab
      capture on 127.0.0.1 only, evaluates the gates, replays it labelled "not part of results.json, not signed",
      and logs it under `atlas_web/data/fresh_handshakes/<run_id>/` (git-ignored). Nothing else is written.
    - With reduced motion (OS setting or the Motion toggle) nothing plays by itself; Step walks the messages.
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
