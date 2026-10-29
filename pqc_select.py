import os
from qpiai_opt.opt_modeller import Binary, Model
from qpiai_opt.opt_solvers import Client, solve

# Systems to migrate: (name, kind, risk_weight, max_bytes_per_handshake)
# risk_weight = how long its secrets must stay safe (harvest-now-decrypt-later)
SYSTEMS = [
    ("tls_gateway",   "kem", 9, 4000),
    ("vpn",           "kem", 8, 3500),
    ("db_encryption", "kem", 10, 6000),
    ("iot_firmware",  "sig", 6, 3000),
    ("code_signing",  "sig", 10, 9000),
    ("doc_signing",   "sig", 7, 6000),
]

# Options: (name, kind, security_level, bytes_on_wire, migration_cost)
# Sizes are NIST parameter sizes; migration_cost is a PLACEHOLDER (1-10 effort).
# Replace with numbers you measure using liboqs.
OPTIONS = [
    ("ML-KEM-512",  "kem", 1, 800 + 768,   2),
    ("ML-KEM-768",  "kem", 3, 1184 + 1088, 3),
    ("ML-KEM-1024", "kem", 5, 1568 + 1568, 5),
    ("ML-DSA-44",   "sig", 2, 1312 + 2420, 3),
    ("ML-DSA-65",   "sig", 3, 1952 + 3309, 4),
    ("ML-DSA-87",   "sig", 5, 2592 + 4627, 6),
    ("Falcon-512",  "sig", 1, 897 + 666,   6),
    ("SLH-DSA-128s","sig", 1, 32 + 7856,   2),
]
BUDGET = 22          # total migration effort available

client = Client(api_key=os.environ["QPIAI_OPT_API_KEY"])
model = Model("pqc_selection")

x = {}
for s in SYSTEMS:
    for o in OPTIONS:
        if o[1] == s[1] and o[3] <= s[3]:          # type match + size limit
            x[(s[0], o[0])] = Binary(f"x_{s[0]}_{o[0]}")

# exactly one algorithm per system
for s in SYSTEMS:
    terms = [v for (sn, on), v in x.items() if sn == s[0]]
    model.add_constraint(sum(terms) <= 1, label=f"max1_{s[0]}")
    model.add_constraint(sum(terms) >= 1, label=f"min1_{s[0]}")

# total migration effort within budget
cost = {o[0]: o[4] for o in OPTIONS}
model.add_constraint(sum(cost[on] * v for (sn, on), v in x.items()) <= BUDGET,
                     label="budget")

# maximize risk-weighted security
sec = {o[0]: o[2] for o in OPTIONS}
risk = {s[0]: s[2] for s in SYSTEMS}
model.maximize(sum(risk[sn] * sec[on] * v for (sn, on), v in x.items()))

r = solve(model, client=client)
print("problem class:", r.problem_class, "| objective:", r.objective)
chosen = {k: v for k, v in r.solution.items() if v > 0.5}
for name in chosen:
    print("  ", name)
