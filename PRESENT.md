# Present Q-Shield Atlas

1. Start: `conda activate pqc && python -m atlas_web --demo --kiosk --port 8000`, then open http://127.0.0.1:8000/ and sign in as admin. `QCLOUD_API_KEY` is read from `.env.sh` and only used for the cloud status check.
2. Check: `python tools/present_check.py` should print READY. Screenshots are saved to `atlas_web/screenshots/present/`.
3. Click path:
   - Landing
   - **Pipeline** "At a glance" (8 stages)
   - **Detect** (weak crypto found)
   - **Proof Chain** (tamper demo)
   - **Plan** (deadline check)
   - **Handshakes**
   - **QAOA**: press *Run QAOA now*; the backend is shown on the result
   - **Bench**
   - **Review**
   - **Move** (replay of the recorded handshakes, sender vs receiver; press Play the plan)
4. The top strip shows the quantum backend in use: "Quantum: Local simulator" or "Quantum: QpiAI Cloud: QpiAI-QSV-Simulator".
5. If QpiAI Cloud is down or disabled, say: "This is running on QpiAI's local simulator; the app is cloud-ready. Cloud login and device list are live, and job submission switches on with the account's subscription."
6. Never say "hardware". QAOA is a simulator cross-check against the exact optimum, with no quantum advantage.
