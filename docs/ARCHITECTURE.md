# Architecture

Detail moved from the README. Short version: [README › Architecture](../README.md#architecture).


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
- `data/real_banks/` is **real**. It holds one polite TLS 1.3 handshake with each of 60 public Indian bank endpoints,
  chosen from the CC0 [bank-in-domains](https://github.com/CCAgentOrg/bank-in-domains) dataset at commit `7b161ae`
  (`python tools/scan_banks.py targets|scan|publish`).
  - Each endpoint is classified as hybrid post-quantum, classical, or unreachable.
  - The scan is signed into the `real-banks` workspace's Proof Chain.
  - Any migration Atlas shows for these endpoints is a planned migration (simulation); no bank system is changed.
- `data/SYNTHETIC_mock_bank_assets.csv` is **synthetic**. It is the fictional 16-asset mock-bank inventory the demo
  schedules. The names are invented and this is not real data.
- Risk, effort and shelf-life values are assumptions (`config/assumptions.json`), not data.
