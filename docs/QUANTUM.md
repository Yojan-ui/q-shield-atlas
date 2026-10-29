# Quantum: QpiAI Opt, QpiAI QSV and QCloud

Every value below is copied from a logged run: `out/results.json` (demo snapshot, assembled 2026-10-29),
the run directories under `runs/<run_id>/` (manifest.json plus raw outputs) and `runs/platform_jobs.log`.
`out/` and `runs/` are git-ignored: rerun the commands at the end to regenerate them. The IBM values come from
the tracked package `data/real_ibm_qaoa/` (merged into main with PR #2).

QAOA here is a measured cross-check against the exact optimum, found by brute force. No quantum advantage is
claimed. The wave problem is small enough for brute force, and that is the point: QAOA can be scored against
a known right answer.


## 1. Install

Project environment (conda env `pqc`, Python 3.12). Both QpiAI SDKs come from the package index and are
pinned in `requirements.txt`:

    conda activate pqc
    pip install -r requirements.txt        # includes qpiai-opt==0.0.9 and qpiai-quantum==0.3.0
    source .env.sh                         # exports QPIAI_OPT_API_KEY and QCLOUD_API_KEY (git-ignored)

Installed and used by the pipeline: `qpiai-opt` 0.0.9 (`import qpiai_opt`) and `qpiai-quantum` 0.3.0
(`import qpiai_quantum`), both in `/opt/anaconda3/envs/pqc/lib/python3.12/site-packages`.

`quantum-sdk/` (git-ignored, reference only) is a clone of the public SDK source. The pipeline does not
import it. The app and pipeline were rerun with it ignored (2026-10-30) and passed (see section 6).

    git clone https://github.com/qpiai/quantum-sdk.git quantum-sdk   # at commit db93cff (v0.7.5-1-gdb93cff)
    python3 -m venv quantum-sdk/.venv                                 # recorded in quantum-sdk/.venv/pyvenv.cfg (Python 3.13.9)

Its own `.venv` holds `qpiai-quantum` 0.7.5 installed by pip. That install has no `direct_url.json`, so it
came from the package index, not from the clone. The project stays on 0.3.0, the version its API notes
(`docs/qpiai_api_notes.md`) were verified against.


## 2. QpiAI Opt: the scheduling MILP

The full migration schedule is a MILP solved by QpiAI Opt in local mode (free, no platform job). The main plan
run in the demo snapshot (`results.json` `solver_runs[0]`):

    stage            schedule.milp.expected.expected
    solver           qpiai-opt local (qpiai-opt 0.0.9, mode local)
    status           optimal (termination optimal, guarantee global_optimum)
    objective        565.3230769230769
    solve time       0.1215455 s
    run_id           641f5d49ae3e4a19b4e2500a0f1047e9
    timestamp        2026-10-29T01:52:01Z
    inputs SHA-256   7eef3f5623c48f3216ef8898601aa03582faa949771c907cb00738eac70aae48
    output SHA-256   abef806293d13c0c3e50c265d901b132bff0e86e4b668c7efcbca7c060d59e77
    job_id           null
    job_id_reason    QpiAI Opt local solve (mode='local') issues no platform job ID; run is traceable via
                     run_id and input/output SHA-256 hashes

The tie-break solve of the same plan (`schedule.milp.expected.tiebreak`, run_id
d4cb2a952acd48b68f7372f7e1c94811) is also optimal, in 0.101248875 s.

Platform mode (`--platform`) stays off. Submissions were rejected on 2026-10-28 with "no active storage quota
found for organization", and no platform job was created.


## 3. QpiAI QSV-Local: the QAOA wave selection

One week's cutover choice becomes a QUBO, and QAOA samples it on the QpiAI SDK's in-process statevector
simulator (`qpiai_quantum.simulator.StatevectorSimulator`, name "QpiAI-QSV-Local": no network, no job, no
credits). Demo snapshot (`results.json` `qaoa`):

    run_id           f8bf1b797021460d96be5efbb1a84acb
    timestamp        2026-10-29T01:52:20Z
    problem          week 1, 10 systems + 4 slack bits = 14 QUBO variables, capacity 10
    exact optimum    objective -0.3461538461538609 = migrate backup and statements (brute force over 2^10 subsets)
    device           qpiai-quantum local simulator, SDK 0.3.0
    shots            2048 per p
    job_id           null ("local SDK simulation issues no job ID")

    p   feasible share   P(optimal set)   best feasible found
    1   0.134765625      0.013671875      exact optimum
    2   0.201171875      0.0185546875     exact optimum
    3   0.17578125       0.01708984375    exact optimum
    uniform random baseline (2048 shots, seed 1007): feasible share 0.00341796875, P(optimal set) 0.0009765625

The same circuits on the project's own numpy statevector simulator agree with QSV-Local within the 4-sigma
threshold at every p (`qaoa.comparisons`, `differs: false`).


## 4. QpiAI QCloud

- Login: works. `QpiAIQuantumAuth.login(QCLOUD_API_KEY)` succeeds, and `JobManager().list_compute_resources()`
  lists QpiAI-QSV-Simulator, QpiAI-QDM-Simulator, QpiAI-QTN-Simulator, QpiAI-QSV-Lite and QpiAI-QDM-Lite
  (active) and QpiAI-Indus-1 (QPU, maintenance) (`docs/qpiai_api_notes.md`). The web app checks this live at
  `GET /api/quantum/status`.
- Job creation: rejected. Two submissions were logged in `runs/platform_jobs.log`, both on QpiAI-QSV-Simulator:
  - 2026-10-28T15:28:55Z, run e3baac4cf6d24a59b6949db08b0cd78d: "Experiment 'qshield-qaoa-crosscheck' not
    found. Please create the experiment first."
  - 2026-10-28T15:29:50Z, run a7985b93f3a5490aaa3636c969dcc1c3: "Bad Request (400) when submitting job.
    Server response: {'error': 'Failed to create job: an active subscription is required to run jobs'}"
- So no QCloud job was created and no QCloud job ID exists. QCloud runs stay disabled
  (`config/atlas_web.json` `platform.qcloud_enabled: false`) until the account has a subscription.
  QpiAI-Indus-1 is refused by code in every mode.


## 5. IBM Quantum ibm_fez: real hardware

The same 14-variable QUBO (circuits tuned on the simulator) was sampled once per p on IBM's ibm_fez QPU.
This is real hardware. It is a measured cross-check, not an advantage claim: hardware noise lowers
feasibility at this circuit depth, and the results show that.

    run_id           152aa6e0425749068e04a75dd332fc4a
    executed_at      2026-10-29T17:07:44Z (on another machine: Windows 11, Python 3.12.10, qiskit 2.6.1,
                     qiskit-ibm-runtime 0.51.0, qpiai-quantum 0.3.0, qpiai-opt 0.0.9)
    signed           ledger entry #3 on the executing machine (qaoa.run, ML-DSA-65)

    p   feasible share   P(optimal set)   transpiled depth   2-qubit gates   QPU s   IBM job ID
    1   0.06640625       0.0087890625     445                337             3       dbhnpos2d77s739d3sv0
    2   0.04443359375    0.00439453125    641                621             3       dbhnpp42d77s739d3svg
    3   0.0146484375     0.0029296875     984                942             3       dbhnppene4hc73bd9480
    uniform random baseline: feasible share 0.00341796875, P(optimal set) 0.0009765625

Source: `data/real_ibm_qaoa/run.json`, `table.csv` and `versions.json`. Full method, safety guards and
reproduction: README section "IBM Quantum hardware run (`ibm_fez`)".


## 6. Reproduce

    conda activate pqc && source .env.sh
    export QSHIELD_FORBID_PLATFORM=1                 # local only (the default in run_demo.sh and pytest)

    # Section 2: QpiAI Opt MILP (local)
    python -m schedule --inventory out/inventory.json

    # Section 3: QAOA on QpiAI-QSV-Local (and the numpy simulator)
    python -m qaoa --qpiai-local

    # Whole pipeline + signed ledger + results.json (attaches the recorded ibm_fez rows; --no-ibm skips that)
    ./run_demo.sh

    # Section 4: QCloud (opt-in, consumes credits; blocked until the account has a subscription)
    ./run_demo.sh --qcloud                           # QpiAI-QSV-Simulator only

    # Section 5 by hand (run_demo.sh already does this): attach the recorded ibm_fez rows without IBM access
    python -m qaoa --qpiai-local --schedule data/real_ibm_qaoa/schedule.json
    python -m qaoa --ibm-import data/real_ibm_qaoa

    # Web app: the Wave selection page shows these four backends as status rows
    python -m atlas_web

Web smoke check, 2026-10-30, with `quantum-sdk/` ignored: server up (`/api/health` 200), full pipeline on the
online-boutique workspace PASS (12/12 steps exit 0), and the QAOA step sampled on "qpiai-quantum local
simulator (QpiAI-QSV-Local)" for p = 1, 2, 3.
