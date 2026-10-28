# atlas_web quality contract

Every remaining stage must satisfy this. Re-read it at the start of each stage.
CLAUDE.md's honesty rules, platform guardrails and locked decisions take precedence over anything here.

## Look: professional, not AI-generated
- Direction: "precision instrument at night". Not an OS (no windows, dock, taskbar, draggable panels),
  not a SaaS card grid.
- Banned AI-template tells: purple/blue gradient blobs, glassmorphism on everything, emoji, sparkle icons,
  "Unlock the power of…" copy, centred hero + three feature cards, generic stock illustrations, rounded pill
  buttons everywhere, drop shadows on every box, lorem ipsum, "coming soon".
- Do instead: strict 12-col grid, hairline 1px rules, asymmetric editorial layouts, tabular monospace
  numerals, uppercase 11px eyebrow labels (0.12em tracking), large confident numbers, generous negative
  space, one accent colour used sparingly, real project terms (HNDL-exposed, X25519MLKEM768, ML-DSA-65,
  exposure-years, wave).
- Every screen: one primary action, designed loading/empty/error/success states, zero layout shift.

## 3D motion: meaningful
- One persistent THE LATTICE world; routes are camera positions. Every motion maps to a real data field
  (state→visual table in the brief). Delete decorative motion with no data behind it.
- Motion tokens in motion.js: camera flights 1.1–1.6 s ease-in-out-cubic with soft settle; overlays 280 ms
  cubic-bezier(.2,.8,.2,1), 60 ms stagger, 24 px rise; exits 180 ms; idle breathing ≤ 1.5 %;
  reduced-motion = crossfades.

## Low latency
- Input→visual response on the next frame (≤ 16 ms). Route change: flight starts next frame, overlay
  ≤ 300 ms after arrival.
- API reads < 50 ms p95. Landing FCP < 1 s, interactive < 1.5 s on localhost. Own JS+CSS+shaders ≤ 250 KB.
- Heavy work off the main thread: layout/geometry prep in a Web Worker with transferable typed arrays;
  the server precomputes a per-workspace scene.json (positions, colours, per-week tower heights) once per
  results change and caches it with an ETag.
- All animation of thousands of elements happens in GLSL vertex shaders driven by uniforms (time, week,
  scenario), not per-frame JS loops over objects. InstancedMesh/Points, ≤ 60 draw calls, DPR ≤ 2, adaptive
  quality, rAF paused when hidden.
- Data loaded once per workspace and kept in a client cache; SSE invalidates/patches it. No refetch on
  route change or scroll.

## Zero errors
- tools/route_check.py: every route at 1440×900, 1280×720, 390×844 as admin, operator, viewer and logged
  out → zero console errors/warnings, zero failed requests, zero unhandled rejections, zero 500s.
- pytest all green, node --check on all JS, node unit tests for router/data/motion.

## Proof per stage
- Screenshots of every route at 3 sizes in atlas_web/screenshots/<stage>/, review.md with a senior-designer
  critique, fix, re-shoot, show before/after of the 3 weakest screens.
- Report: pytest count, route_check result, API p95, FCP, fps + worst frame, asset size, commit hash.
