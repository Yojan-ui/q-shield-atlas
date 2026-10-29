import os
from qpiai_quantum.authentication import QpiAIQuantumAuth

QpiAIQuantumAuth.login(os.environ["QCLOUD_API_KEY"])
import runpy

from qpiai_opt.opt_solvers import solve
from qpiai_opt.quantum import QAOA, XYMixer
from qpiai_opt.quantum._shared import QUBOProblem


print("\n========== LOADING EXISTING PQC MODEL ==========")

# Reuse the existing systems, options, constraints and objective.
# This also runs your original classical optimization script.
ns = runpy.run_path("pqc_select.py")

model = ns["model"]
systems = ns["SYSTEMS"]
options = ns["OPTIONS"]
budget = ns["BUDGET"]

# Explicitly convert the constrained model into QUBO.
qubo = QUBOProblem.from_model(model)
names = list(qubo.variable_names)
name_to_idx = {name: i for i, name in enumerate(names)}

print("QUBO variables:", len(names))
print("Migration budget:", budget)

# Build one XY-mixer group per system using the actual
# variable names created by pqc_select.py.
groups = []
initial_state = [0] * len(names)
name_to_choice = {}

for system in systems:
    system_name, system_kind, risk, max_bytes = system
    indices = []

    for option in options:
        option_name, option_kind, security, byte_size, cost = option

        if option_kind != system_kind or byte_size > max_bytes:
            continue

        variable_name = f"x_{system_name}_{option_name}"

        if variable_name not in name_to_idx:
            continue

        idx = name_to_idx[variable_name]
        indices.append(idx)
        name_to_choice[variable_name] = (system, option)

    if not indices:
        raise RuntimeError(
            f"No eligible QUBO variables for {system_name}"
        )

    groups.append(indices)

    # Start in a one-hot state for every system.
    initial_state[indices[0]] = 1

print("Systems:", len(systems))
print("XY mixer groups:", len(groups))

# Run QAOA on the local simulator.
groups = [list(range(len(names)))]

algorithm = QAOA(
    reps=2,
    initial_state=initial_state,
    mixer=XYMixer(groups=groups, topology="ring"),
)

print("\n========== RUNNING QAOA ON QPIAI PLATFORM ==========")

result = solve(
    qubo,
    mode="platform",
    algorithm=algorithm,
)

print("Raw QAOA objective:", result.objective)

# Decode either a mapping or a bit-vector solution.
raw_solution = result.solution

if isinstance(raw_solution, dict):
    if all(name in raw_solution for name in names):
        bits = [raw_solution.get(name, 0) for name in names]
    else:
        bits = [
            raw_solution.get(i, raw_solution.get(str(i), 0))
            for i in range(len(names))
        ]
else:
    bits = list(raw_solution)

if len(bits) != len(names):
    raise RuntimeError(
        f"Solution length {len(bits)} does not match "
        f"QUBO variable count {len(names)}"
    )

selected = [
    name for name, value in zip(names, bits)
    if float(value) > 0.5 and name in name_to_choice
]

print("\n========== DECODED MIGRATION PLAN ==========")

selected_by_system = {}
for name in selected:
    system, option = name_to_choice[name]
    selected_by_system.setdefault(system[0], []).append(option)

total_cost = 0
total_security_score = 0
valid = True

for system in systems:
    system_name, system_kind, risk, max_bytes = system
    choices = selected_by_system.get(system_name, [])

    if len(choices) != 1:
        print(f"INVALID: {system_name} has {len(choices)} selections")
        valid = False
        continue

    option = choices[0]
    option_name, option_kind, security, byte_size, cost = option

    total_cost += cost
    total_security_score += risk * security

    print(
        f"{system_name}: {option_name} | "
        f"security={security} | bytes={byte_size} | cost={cost}"
    )

if total_cost > budget:
    print(f"\nINVALID: cost {total_cost} exceeds budget {budget}")
    valid = False

if valid:
    print("\nFEASIBLE under checked selection and budget rules.")
else:
    print("\nNO FEASIBLE PLAN decoded. Do not use this selection.")

print("Total migration cost:", total_cost, "/", budget)
print("Original risk-weighted security score:", total_security_score)
print("Note: migration costs are prototype placeholders.")
