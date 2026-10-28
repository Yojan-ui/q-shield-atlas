# Next: showcase website (`site/`), not started yet

Paste this into Claude Code from the repo root. Follow CLAUDE.md.

Build site/: a showcase website for Q-Shield Atlas. Distinctive, lightweight, wired to the real backend.

## Concept: "The Lattice"
One full-screen WebGL canvas, scroll-driven. The camera flies through a 3D lattice (a nod to ML-KEM's lattice
security). Each scroll chapter is a scene the camera enters; DOM text overlays stay minimal and readable.
No hero banner, no card grid, no template look.

## Chapters (all data from the backend, never hard-coded)
1. HARVEST: instanced packet particles stream into a dark vault ("harvest now, decrypt later"). A Q-day dial snaps
   between the Z scenarios in results.json (2030/2032/2035) and the vault's exposure glow updates.
2. DETECT: the codebase as a city of instanced columns (one per file). Findings glow red at height = line number;
   hover shows file:line + algorithm. Decoys stay dark.
3. SCHEDULE: the exposure tower. Floors collapse week by week as you scroll; ghost towers for FCFS and greedy collapse
   slower beside it. An exposure-years-avoided counter driven by the real values.
4. HANDSHAKE: two particle strands (X25519 + ML-KEM-768) braid into one hybrid strand for the hybrid and pq-auth services;
   legacy shows a single strand with the red HNDL beam. A classical-only client hits a wall (downgrade refused).
5. LEDGER: the Merkle tree crystallises leaf by leaf (one leaf per real entry, root hash on top). "Tamper a copy" calls
   the backend, which edits a COPY of the ledger, runs verify and returns the failing index; that branch cracks red.
   The real ledger is never touched.
6. QAOA: a probability cloud over bitstrings for p=1..3. QAOA mass concentrates on the optimal set vs a flat random cloud,
   from the real metrics. Label: "measured cross-check, no quantum advantage". QCloud rows show their status_text.
7. CLOSE: the lattice zooms out into the project name, with `./run_demo.sh`, repo/release links and the honesty footer.

## Backend (stdlib only, `python -m site`)
- http.server bound to 127.0.0.1 on a free port, serving ONLY site/ plus read-only JSON: /api/results, /api/ledger
  (entries, root, verify status), /api/handshakes. Same rule as viz/: never serve the repo root; keys/, .env.sh and
  runs/ must stay unreachable (add a test that requests them and gets 404).
- Server-Sent Events at /api/events: watch out/results.json and the ledger mtime. When run_demo.sh finishes, the open page
  animates to the new values with no reload.
- POST /api/tamper-demo: copy the ledger to a temp dir, flip one byte, verify the copy, return {index, reason}, delete the
  copy. Never touches the real ledger. Rate-limited to 1 request per second.
- `python -m site export` writes a static snapshot (data embedded as JSON) to site/dist/ for GitHub Pages; the tamper
  button there replays a recorded result, clearly labelled "recorded".

## Performance ("zero latency", stated honestly)
- Data loaded once at start plus SSE pushes: no request happens on scroll; interaction responds on the next frame.
- Reuse the vendored, hash-checked three.js in viz/vendor. No other libraries, no build step, no CDN, no web fonts.
- Own JS+CSS+shaders ≤ 150 KB unminified. InstancedMesh/Points only, ≤ 50 draw calls, one requestAnimationFrame loop,
  devicePixelRatio capped at 2, paused when the tab is hidden.
- 60 fps target on an M-series MacBook, usable on a mid-range phone; fps meter behind ?debug.
- prefers-reduced-motion → static camera with crossfades. No WebGL → fall back to the existing 2D viz page.

## UX
Scroll and keyboard (↑/↓, space) drive chapters; a slim chapter rail; every number has a provenance tooltip
(run_id / job_id / ledger index); readable at 1280×720 on a projector; aria-live text summary for each scene.

## Tests (Python)
Every number the site renders exists in /api/results; the tamper demo never modifies the real ledger (hash before and
after); SSE pushes on a file change; the static export has no absolute local paths or secrets; own assets within the
size budget; vendored hashes match.

Build in stages (backend + data layer → chapters 1–3 → 4–7 → performance pass). Show screenshots per chapter, measured
fps, asset sizes, the pytest summary and the commit hash.
