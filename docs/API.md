# atlas_web API

Every route below is handled in `atlas_web/server.py` (`api()`, `auth()`, `users()`, `workspaces()`); nothing else
is served under `/api/`. The server binds 127.0.0.1.

- **Roles:** viewer < operator < admin (`atlas_web/auth.py`). "public" means no session is needed.
- **Writes:** every non-GET request (except login) needs the `X-CSRF-Token` header to match the `atlas_csrf` cookie.
- **Events:** `events` routes are Server-Sent Events streams.
- **Demo:** the `demo` workspace is the repo's `out/` + `runs/`, read-only. Its results, ledger, report and scene
  are public, so the landing page can tell its story without a session.

## Session, users and service

| METHOD | PATH | PURPOSE | ROLE |
|---|---|---|---|
| GET | `/api/health` | liveness: `{ok, service, time}` | public |
| POST | `/api/auth/login` | sign in (JSON body); sets the session cookie (HttpOnly) and the CSRF cookie | public |
| POST | `/api/auth/logout` | sign out; clears both cookies | signed-in user |
| GET | `/api/me` | current user, plus kiosk and demo flags | public |
| GET | `/api/stages` | the stage list from `contracts/stages.json` | public |
| GET | `/api/events?ws=<id>` | SSE: the workspace's output files changed | viewer |
| GET | `/api/preflight[?ws=<id>]` | environment checks before a run | operator |
| GET | `/api/reference-endpoints` | the public PQ reference endpoints preset (`config/atlas_web.json`) | viewer |
| GET | `/api/quantum/status` | QpiAI backend status: QCloud login, device list, and the blocker reason when disabled | viewer |
| POST | `/api/quantum/run` | one live QAOA run of the link cutover step (QCloud only if enabled, else QpiAI-QSV-Local) | viewer |
| GET | `/api/users` | list users | admin |
| POST | `/api/users` | create a user | admin |
| DELETE | `/api/users/<name>` | delete a user (not yourself) | admin |

## Workspaces

| METHOD | PATH | PURPOSE | ROLE |
|---|---|---|---|
| GET | `/api/workspaces` | list workspaces and templates | viewer |
| POST | `/api/workspaces` | create a workspace from a template | operator |
| GET | `/api/workspaces/<ws>` | workspace summary | viewer |
| GET | `/api/workspaces/<ws>/results` | `out/results.json` | viewer (public for `demo`) |
| GET | `/api/workspaces/<ws>/scene` | the 3D scene derived from results (ETag) | viewer (public for `demo`) |
| GET | `/api/workspaces/<ws>/inventory` | `out/inventory.json` (Detect graph) | viewer |
| GET | `/api/workspaces/<ws>/ledger` | ledger entries and live verification | viewer (public for `demo`) |
| GET | `/api/workspaces/<ws>/ledger/proof/<n>` | Merkle inclusion proof for entry n | viewer (public for `demo`) |
| GET | `/api/workspaces/<ws>/report` | `out/report.html` (strict CSP) | viewer (public for `demo`) |
| POST | `/api/workspaces/<ws>/tamper-demo` | edit a temporary ledger copy and verify it; the real ledger is untouched (1 per second) | viewer |
| GET | `/api/workspaces/<ws>/move` | recorded handshakes as message lists (Migration page) | viewer |
| POST | `/api/workspaces/<ws>/move/fresh` | fresh lab handshake on 127.0.0.1 (if enabled in config) | operator |
| GET / POST | `/api/workspaces/<ws>/reviews` | items awaiting review / sign a decision into the Proof Chain | viewer / operator |
| GET / PUT | `/api/workspaces/<ws>/estimate` | time estimate vs the deadline / save the deadline | viewer / operator |
| GET / POST | `/api/workspaces/<ws>/bench` | benchmark results / run `python -m bench`, sign it, verify the chain | viewer / operator |
| GET / POST | `/api/workspaces/<ws>/manifests` | service manifests / save them | viewer / operator |
| POST | `/api/workspaces/<ws>/manifests/suggest` | suggest manifests from the cloned source | operator |
| POST | `/api/workspaces/<ws>/manifests/confirm` | confirm the suggested manifests (runs are refused until then) | operator |
| GET / PUT, POST | `/api/workspaces/<ws>/assumptions` | assumptions (labelled "assumption") / save them | viewer / operator |
| GET / POST | `/api/workspaces/<ws>/calibration` | calibration proposal / record measurements | viewer / operator |
| POST | `/api/workspaces/<ws>/calibration/apply` | apply calibration: re-plan, sign `calibration.apply` | operator |
| POST | `/api/workspaces/<ws>/upload` | .zip source upload (zip-safety checks, nothing executed) | operator |
| POST | `/api/workspaces/<ws>/clone` | shallow clone of a public https repository | operator |
| GET | `/api/workspaces/<ws>/runs` | the last 50 runs and the active run | viewer |
| POST | `/api/workspaces/<ws>/runs` | start the pipeline (probes, presets; platform/QCloud admin-only and disabled) | operator |
| GET | `/api/workspaces/<ws>/runs/<run_id>` | one run's record | viewer |
| GET | `/api/workspaces/<ws>/runs/<run_id>/events` | SSE: live run log, or a replay of a finished run | viewer |

Writes to `demo` are refused (read-only). A run already in progress in a workspace blocks uploads, clones and new runs
(409).
