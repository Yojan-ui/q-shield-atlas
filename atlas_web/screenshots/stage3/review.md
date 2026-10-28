# Stage 3 design review (design system, router, shell)

Reviewed every screenshot at 1440×900, 1280×720 and 390×844 (admin on every route; signed out on the public
routes and the guard redirect; viewer on the 403). Critique written as a senior product designer, then fixed
and re-shot. Screens are 2D overlays only: THE LATTICE (Stage 4) will fill the reserved world layer.

## Round 1: findings

| # | screen | problem | severity | fix |
|---|---|---|---|---|
| 1 | every route, 1440 + 1280 | Top strip collides: the 200 px workspace select runs into the rail, and the rail's last item runs into a redundant "Run pipeline" button. Looks broken. | blocker | Removed the strip Run button (the pipeline page owns the one primary action), fixed select width with ellipsis, explicit grid columns, rail labels shortened ("QAOA"), key hints and "Workspace" label drop below 1360 px. |
| 2 | landing + sign-in, signed out | Workspace select (empty), rail and Run button visible when signed out: `[hidden]` lost to `display:flex`. | blocker | Global `[hidden] { display: none !important }`; "Sign in" pinned to the right edge. |
| 3 | every route, 390 | Bottom rail never docked: `backdrop-filter` on the strip made it the containing block of the fixed rail, so the rail rendered inside the strip and "Sign out" wrapped to a second row. | blocker | Blur moved to `.strip::before`; mobile strip = wordmark · workspace · sign out; bottom bar uses short labels (Pipeline, Detect, Plan, TLS, Ledger, QAOA). |
| 4 | every route | Programmatic focus on the route heading drew a 2 px cyan box around the H1 (looks like a selection bug). | major | `h1[tabindex="-1"]:focus { outline: none }`: focus still moves to the heading (screen readers announce it), keyboard focus rings elsewhere are unchanged. |
| 5 | landing, asset | Focus fell back to `<body>` because the H1 rendered after data arrived (caught by route_check). | major (a11y) | H1 renders on first paint; data only updates its text. |
| 6 | pipeline | Stations offset 40 px by the default `<ol>` padding; numbers misaligned with the hairline grid. | major | List reset on `.stations`. |
| 7 | pipeline (demo) | A 320 px empty console saying "No output yet." reads as unfinished on a read-only snapshot. | major | Replaced with a sentence saying where the snapshot's logs are and that runs started here stream line by line. |
| 8 | pipeline | Status chip mangled `run_demo.sh` into "run demo.sh" (underscore replacement applied to free text). | minor | Underscores replaced only for status keys, never for supplied text. |
| 9 | landing | 64 px headline wrapped to four lines in 7 columns; heavy. | minor | 8 columns, three lines; aside copy tightened to avoid an orphan. |
| 10 | detect / ledger, 390 | Wide tables squeezed the service name into four lines. | minor | Columns marked optional (kind, data class, algorithm, rule, snippet, payload, time) hide below 760 px; full data stays in the 1440/1280 layouts and on the asset page. |
| 11 | contrast test | Tertiary text #55606B (from the brief) is 3.06:1 on the base, and #6F7B87 still failed on raised and tinted surfaces. | blocker (AA) | `--text-3: #7A8692`, the darkest value passing 4.5:1 on every surface; the test asserts the brief value fails, so the deviation is explicit. |

## Before / after (the three weakest screens)

| screen | before | after |
|---|---|---|
| Shell on every route (shown: pipeline 1440) | `before/1440_admin__w_demo_pipeline.png` | `1440x900/admin__w_demo_pipeline.png` |
| Mobile (shown: detect 390) | `before/390_admin__w_demo_detect.png` | `390x844/admin__w_demo_detect.png` |
| Landing, signed out 1440 | `before/1440_anon__landing.png` | `1440x900/anon__landing.png` |
| (also) Sign-in 1440 | `before/1440_anon__signin.png` | `1440x900/anon__signin.png` |

## Checklist after round 2

- Grid: content on the 12-column grid with 24 px gutters (16 px on phones); stats and stations share hairlines.
- Spacing: only tokens from tokens.css; app.css has no literal colours.
- Text never overlaps the (reserved) 3D layer; no horizontal page scroll at any size (route_check asserts it).
- Truncation: workspace names ellipsise in the select only; table columns hide rather than truncate on phones.
- Contrast: every text/background pair ≥ 4.5:1 (node test).
- Hierarchy: one primary action per screen (Run pipeline, Tamper a copy, Open pipeline in empty states, Create user, Sign in).
- States: skeletons match the final layout (stat row, tables); empty states for un-run workspaces; error state with retry; 404 and 403 designed.

## Known and deferred

- 404 and sign-in are deliberately sparse: Stage 4 places the broken cell and the locked cell in THE LATTICE.
- Detect's column city, the schedule tower, handshake strands, Merkle tree and QAOA cloud are Stage 4–6 scenes; Stage 3 shows the same data as tables.
- The schedule solver label shows only recorded fields ("QpiAI Opt · local MILP · optimal · global optimum"); "HiGHS" is not recorded per run in results.json, so it is not shown.
