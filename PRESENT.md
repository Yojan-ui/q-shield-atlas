# Present Q-Shield Atlas

1. Start: `conda activate pqc && python -m atlas_web --demo --kiosk --port 8000`, then open http://127.0.0.1:8000/ and sign in as admin. `QCLOUD_API_KEY` is read from `.env.sh` and only used for the cloud status check.
2. Check: `python tools/present_check.py` should print READY. Screenshots are saved to `atlas_web/screenshots/present/`.
3. Click path (the backend's run order):
   - **Landing**: headline, three real numbers, 3D; press *See it run* (guided replay on the demo)
   - **Overview**: the 7 steps lit from the real run status; on a real workspace press *Run pipeline* and follow the guided 3D run
   - **1 Detect** (findings -> systems, drift; Inventory & drift is part of this step)
   - **2 Proof chain opened** (Ledger page: chain verified before append; tamper test)
   - **3 Plan** (comparison chart, objective by Q-Day, why MILP, solver quality)
   - **4 Handshake gates**
   - **5 Wave selection**: press *Run QAOA now*; the backend is shown on the result
   - **6 Proof verified** (Ledger page: every record re-verified)
   - **7 Review**
   - More: **Move** (sender vs receiver replay), **Benchmark**; press **P** anywhere for presenter mode
4. The top strip shows the quantum backend in use: "Quantum: Local simulator" or "Quantum: QpiAI Cloud: QpiAI-QSV-Simulator".
5. If QpiAI Cloud is down or disabled, say: "This is running on QpiAI's local simulator; the app is cloud-ready. Cloud login and device list are live, and job submission switches on with the account's subscription."
6. Never say "hardware". QAOA is a simulator cross-check against the exact optimum, with no quantum advantage.
