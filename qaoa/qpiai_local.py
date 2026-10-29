"""Free local sampling of the final QAOA circuits with the QpiAI SDK's in-process simulator
(python -m qaoa --qpiai-local).

QAOA on simulators. A measured cross-check against the exact optimum. No quantum advantage
claimed; the problem is small enough for brute force.

Uses qpiai_quantum.simulator.StatevectorSimulator (device name "QpiAI-QSV-Local", verified in the
installed qpiai-quantum 0.3.0): it runs the same qpiai_quantum.Circuit that --qcloud would submit,
entirely in this process. No login, no network, no credits, so no platform guard is involved. Local
SDK simulation issues no job ID: each record carries job_id null with a reason, our run_id and
SHA-256 hashes of the exact inputs and of the counts.
"""

import importlib.metadata as md
import json
from pathlib import Path

from contracts.manifest import sha256_json

from .circuit import build_circuit

BACKEND = "qpiai-quantum local simulator"
JOB_ID_REASON = "local SDK simulation issues no job ID"


def run(q, angle_sets: list[dict], cfg: dict, run_id: str, run_dir: Path) -> list[dict]:
    """angle_sets: [{"p", "gammas", "betas", "energy_scale"}] (the numpy-optimised angles). One record per p."""
    from qpiai_quantum.simulator import StatevectorSimulator

    sim = StatevectorSimulator()
    version = md.version("qpiai-quantum")
    records = []
    for a in angle_sets:
        seed = cfg["seed"] + 2000 + a["p"]
        inputs = {"qubo_linear": list(map(float, q.linear)), "qubo_quad": sorted([list(k) + [float(v)] for k, v in q.quad.items()]),
                  "gammas": a["gammas"], "betas": a["betas"], "energy_scale": a["energy_scale"], "shots": cfg["shots"],
                  "seed": seed, "device": sim.name, "sdk": f"qpiai-quantum {version}"}
        res = sim.run(build_circuit(q, a["gammas"], a["betas"], a["energy_scale"]), shots=cfg["shots"], seed=seed)
        counts = {str(k): int(v) for k, v in (res.counts or {}).items()}
        rec = {"p": a["p"], "status": "ok", "backend": f"{BACKEND} ({sim.name})", "sdk_version": version, "device": sim.name,
               "run_id": run_id, "job_id": None, "job_id_reason": JOB_ID_REASON, "seed": seed, "shots": cfg["shots"],
               "inputs_sha256": sha256_json(inputs), "outputs_sha256": sha256_json(counts), "counts": counts}
        (run_dir / f"qpiai_local_p{a['p']}.json").write_text(json.dumps({**rec, "inputs": inputs}, indent=1))
        records.append(rec)
    return records
