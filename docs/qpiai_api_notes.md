# QpiAI API notes (verified 2026-10-28)

Inspected from installed source in conda env `pqc` (Python 3.12.16) and a live smoke test.
Only names listed here are known to exist.

## Packages
| dist | version | import |
|---|---|---|
| qpiai-opt | 0.0.9 | `qpiai_opt` |
| qpiai-quantum ("QCloud" SDK) | 0.3.0 | `qpiai_quantum` |

## Modelling — `qpiai_opt.opt_modeller`
- Variables: `Binary(name)`, `Integer(name, lower_bound=0, upper_bound=None)`,
  `Continuous(name, lower_bound=0.0, upper_bound=inf)` (note: `lower_bound`, not `lb`),
  also `IndexedVariables`, `create_binary_array`, `quicksum(items)`.
- `Model(name)`: `.minimize(expr)`, `.maximize(expr)`, `.add_constraint(rel, label=...)`,
  `.is_feasible(...)`, `.constraint_violations(...)`, `.evaluate_objective(...)`,
  `.to_qubo_dict()`, `.to_lp_string()`, `.summary()`, `.compile(target=...)`.

## Classical solving — `qpiai_opt.opt_solvers`
- `Client(api_key=...)`; `solve(problem, mode="local"|"platform"|"auto", client=..., allow_platform=False, **options)`.
- `mode="local"` (default): free, but verifies the Opt key online first. No job ID is issued
  (`job_id=None`, `problem_id=None`). `model_status` reports the HiGHS status string, i.e. the
  local MILP runtime is HiGHS-based.
- `mode="platform"`: creates a problem + job on `https://opt-server.qpiai.tech/api`, returns
  `job_id`/`problem_id`, **can consume credits**. Nonblocking: `submit()`, `status()`, `result()`, `cancel()`.
- MILP result fields: `problem_class, execution_mode, sense, status, model_status, objective,
  solution (dict name->value), job_id, problem_id, solver_time_s, compute_time_s, solve_info`.
  `result.info()` -> `.method, .termination, .guarantee` (e.g. `optimal`, `global_optimum`).
- Helpers: `classify, inspect, feasibility, provider_capabilities, schemas, LOCAL_LIMITS`
  (MILP local limit: 20 000 vars / 20 000 constraints).

Live smoke test: 3-var MILP, local -> `status=optimal`, `guarantee=global_optimum`, `job_id=None`.

Platform account checks (2026-10-28):
- `Client.get_user_quotas()` -> `APIError: secret token is not permitted for this endpoint`
  (credit/quota balance not readable with an API key).
- `solve(model, mode="platform", ...)` -> `APIError: no active storage quota found for organization`.
  MILP platform solves upload the LP model to storage first; the account has no storage quota.
- `Client.list_jobs()` / `list_problems()` work (read-only): 0 jobs, 0 problems after the failure.
- Platform MILP accepts the same `time_limit` / `mip_rel_gap` options (mapped to `MILPSolverConfig`).

## Gate-based optimisation — `qpiai_opt.quantum`
- `QAOA(reps=1, parameterization="standard"|"multi_angle", optimizer="cobyla"|"spsa"|"nelder_mead"|"powell"|callable,
  max_iterations=100, initial_point=None, aggregation=CVaR|None, warm_start=None, mixer=XYMixer|callable|None, initial_state=None)`.
  Also `VQE, SamplingVQE, RecursiveQAOA, ADAPTQAOA, CVaR, WarmStart, XYMixer`.
- Execution: `solve(problem, mode="local"|"platform", algorithm=QAOA(...), execution=QuantumRun(...))`.
- `QuantumRun(shots=1024, experiment_name=None, timeout=None (platform only), seed=None (local only), device_name=None (platform only))`.
- `mode="local"` -> in-process `QpiAI-QSV-Local` statevector simulator; requires
  `QpiAIQuantumAuth.login(QCLOUD_API_KEY)` (verified online), no cloud job.
- `mode="platform"` -> `circuit.run(device_name=...)` on QCloud, one job **per optimizer
  evaluation**; can consume credits. **Default device is `QpiAI-Indus-1` (QPU)** — always pass
  `QuantumRun(device_name="QpiAI-QSV-Simulator")`.
- `QpiAIQuantumAuth` is re-exported from `qpiai_quantum`.
- `QUBOProblem` lives in `qpiai_opt.quantum._shared` (private module; `QUBOProblem.from_model(model)`).
- `QuantumResult`: `objective, solution, variable_assignment, quantum: QuantumDiagnostics`.
  `QuantumDiagnostics`: `backend, shots, optimizer, evaluations, iterations, optimized_parameters,
  objective_history, counts (final circuit), candidates: list[QuantumSample], job_ids, qpu_metadata,
  logical_circuit, algorithm_metadata`.
  `QuantumSample`: `bitstring, count, probability, internal_energy, objective, feasible, solution, variable_assignment`.
  Note: `candidates` aggregate counts over *all* variational evaluations; `counts` is the final circuit only.

## QCloud devices (live `JobManager().list_compute_resources()`)
| device | status |
|---|---|
| QpiAI-QSV-Simulator | active |
| QpiAI-QDM-Simulator | active |
| QpiAI-QTN-Simulator | active |
| QpiAI-QSV-Lite | active |
| QpiAI-QDM-Lite | active |
| QpiAI-Indus-1 (QPU) | maintenance |

`max_qubits` is reported as 0 for all, so simulator qubit limits are not known from the API.

## PQC crypto backends (env `pqc`)
- liboqs-python 0.16.0.1 / liboqs 0.16.0: ML-DSA-44/65/87, ML-KEM-512/768/1024.
- cryptography 50.0.2 (bundled OpenSSL 4.0.3): `cryptography.hazmat.primitives.asymmetric.mldsa` (ML-DSA-44/65/87).
- `openssl` CLI in env `pqc`: 3.6.5 (has ML-DSA / ML-KEM). System `openssl` is 3.0.18 (no PQC).
