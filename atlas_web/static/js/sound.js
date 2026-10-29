// Optional sound (muted by default; the choice is remembered per browser). WebAudio-synthesised, no files; nothing
// plays before the user turns it on (a user gesture). Hum under the landing, tick per wave flip, chord when the
// ledger verifies, crack on tamper.
let ctxA = null, on = false, hum = null;
try { on = localStorage.getItem("atlas.sound") === "on"; } catch { on = false; }

function ac() { if (!ctxA) ctxA = new AudioContext(); return ctxA; }
function tone(freq, dur, { type = "sine", gain = 0.04, when = 0, slide = null } = {}) {
  if (!on) return;
  const a = ac(), o = a.createOscillator(), g = a.createGain(), t = a.currentTime + when;
  o.type = type; o.frequency.setValueAtTime(freq, t);
  if (slide) o.frequency.exponentialRampToValueAtTime(slide, t + dur);
  g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g).connect(a.destination); o.start(t); o.stop(t + dur + 0.02);
}

export const sound = {
  get on() { return on; },
  toggle() {
    on = !on;
    try { localStorage.setItem("atlas.sound", on ? "on" : "off"); } catch { /* private mode: not remembered */ }
    if (!on) this.hum(false);
    return on;
  },
  tick() { tone(1320, 0.05, { gain: 0.025, type: "triangle" }); },
  chord() { [523.25, 659.25, 783.99].forEach((f, i) => tone(f, 0.9, { gain: 0.02, when: i * 0.03 })); },
  crack() { tone(160, 0.25, { type: "sawtooth", gain: 0.05, slide: 50 }); },
  hum(start) {
    if (!start || !on) { if (hum) { hum.stop(); hum = null; } return; }
    if (hum) return;
    const a = ac(), g = a.createGain(); hum = a.createOscillator();
    hum.frequency.value = 55; g.gain.value = 0.012; hum.connect(g).connect(a.destination); hum.start();
  },
};
