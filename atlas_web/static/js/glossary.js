// Glossary: plain definitions for every technical term the UI uses. term() renders a dotted-underline link to
// /glossary#id with the short definition as its tooltip.
import { h } from "./dom.js";

export const GLOSSARY = [
  { id: "pqc", term: "Post-quantum cryptography", short: "Encryption designed to stay secure even against a large quantum computer.",
    long: "New public-key algorithms standardised by NIST in 2024 (FIPS 203, 204). They replace RSA and elliptic-curve crypto. This is not QKD: it runs on ordinary computers and networks." },
  { id: "hndl", term: "Harvest now, decrypt later", short: "Recording encrypted traffic today to break it once a quantum computer exists.",
    long: "Traffic protected only by classical key exchange can be stored now and decrypted in future. Data that must stay secret for years is exposed today. Atlas labels such sessions \"HNDL-exposed\"." },
  { id: "tls", term: "TLS handshake", short: "The first messages of a secure connection, where both sides agree on keys.",
    long: "Atlas records the handshake only: which key-exchange group and certificate were used. It never records keys or decrypts traffic." },
  { id: "hybrid", term: "Hybrid key exchange", short: "Classical and post-quantum key exchange combined, so both must be broken.",
    long: "X25519MLKEM768 combines X25519 (classical) with ML-KEM-768 (post-quantum). It protects recorded traffic against a future quantum computer while staying compatible." },
  { id: "mlkem", term: "ML-KEM", short: "The NIST post-quantum key-exchange algorithm (FIPS 203), formerly Kyber.",
    long: "Used inside hybrid TLS as X25519MLKEM768. ML-KEM-768 targets NIST security category 3." },
  { id: "mldsa", term: "ML-DSA", short: "The NIST post-quantum signature algorithm (FIPS 204), formerly Dilithium.",
    long: "Atlas signs every Proof Chain record with ML-DSA-65 (OpenSSL 3.6.5), so the record itself is quantum-safe." },
  { id: "rsa-ecc", term: "RSA and ECC", short: "Today's public-key algorithms; a large quantum computer could break them (Shor's algorithm).",
    long: "Includes RSA, ECDSA, ECDH and X25519. They are what Detect looks for." },
  { id: "milp", term: "MILP", short: "Mixed-integer linear programming: exact optimisation with a proof of the best answer.",
    long: "Atlas plans the migration as a MILP solved by QpiAI Opt. The solver reports \"global optimum\" when it has proven no better plan exists." },
  { id: "qubo", term: "QUBO", short: "A yes/no optimisation problem written as a quadratic formula; the input format for QAOA.",
    long: "Atlas turns one week's choice (which systems cut over now) into a QUBO of at most 16 variables." },
  { id: "qaoa", term: "QAOA", short: "A quantum algorithm for optimisation problems written as a QUBO.",
    long: "Atlas runs QAOA on simulators only and compares it with the exact answer. It is a cross-check; no quantum advantage is claimed." },
  { id: "ledger", term: "Proof Chain", short: "A tamper-evident, signed log of every result (the ledger).",
    long: "Each record is hashed into a chain with a Merkle root and signed with ML-DSA-65. Changing any byte makes verification fail at that record." },
  { id: "wave", term: "Wave", short: "A group of systems migrated in the same week.",
    long: "Each wave passes lab gates (post-quantum handshake, downgrade refused, compatibility, tested rollback) before it counts as verified." },
  { id: "crqc", term: "Q-Day (CRQC)", short: "The day a cryptographically relevant quantum computer exists.",
    long: "Its date is unknown. Atlas plans against several assumed years (scenarios) instead of one guess." },
];
const BY = Object.fromEntries(GLOSSARY.map((g) => [g.id, g]));

export function term(id, text = null) {
  const g = BY[id];
  if (!g) return text || id;
  return h("a", { class: "term", href: `/glossary?term=${id}`, title: g.short, "aria-label": `${text || g.term}: ${g.short}` }, text || g.term);
}
