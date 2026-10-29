# Real banks: public TLS observation (data dictionary)

**What this is.** One TLS 1.3 handshake with each of 60 public web endpoints of Indian banks, recorded on 2026-10-29.
- It shows which key exchange each endpoint negotiates today.
- It is an observation, not a security assessment of any bank.
- Any migration shown in Atlas for these endpoints is a **planned migration — simulation**. Nothing was changed at any bank.

**Source dataset.**
- [CCAgentOrg/bank-in-domains](https://github.com/CCAgentOrg/bank-in-domains), CC0 1.0.
- Pinned commit `7b161ae37caa39703db0e9fd6b51ab8521a02da4`, file `data/bank_domains_status.csv`.
- The SHA-256 of every CSV in the dataset is in `dataset.json`.

**Selection** (`tools/scan_banks.py targets`, deterministic):
- Only rows with `https_works == True`.
- Hosts whose name contains uat, dev, test, stg, staging, sit, preprod, cug, internal, vpn or admin are excluded.
- Per bank, at most 3 endpoints, and only the apex, `www.` and `netbanking.` hosts.
- Banks are taken in SHA-256(bank name) order, a reproducible spread rather than a ranking, until 60 hosts are reached.

**Probe** (`tools/scan_banks.py scan`):
- `detect/live_probe.probe(host, 443)` runs one `openssl s_client` handshake (OpenSSL 3.6.5) offering X25519MLKEM768, X25519 and P-256.
- 8 s timeout, at most 4 at a time.
- No HTTP request, no other port, no retry.
- Transcripts and public leaf certificates are kept in git-ignored `runs/real_banks/<run_id>/`.
- The scan manifest (`scan_<date>.manifest.json`) is signed into the `real-banks` workspace's Proof Chain as `bank_scan.run`.

## targets.csv

| Column | Meaning | Unit / values |
|---|---|---|
| bank | Bank label: the name before `.bank.in` | text |
| host | Host name probed | DNS name |
| endpoint | Which public endpoint | apex / www / netbanking |
| port | TCP port | 443 |
| source_row_status_code | HTTP status the dataset recorded for this host (not re-checked) | integer |
| dataset_commit | Dataset commit the row came from | 40-hex |

## scan_<date>.csv

| Column | Meaning | Unit / values |
|---|---|---|
| bank, host, endpoint, port | As in targets.csv | |
| observed_at_utc | Time of the handshake | ISO 8601 UTC |
| outcome | `hybrid_pq`: post-quantum hybrid key exchange (X25519MLKEM768). `classical`: classical only, quantum-vulnerable. `unreachable`: no handshake within 8 s | enum |
| tls_version | Negotiated protocol | e.g. TLSv1.3 |
| negotiated_group | Key-exchange group the server chose | IANA name |
| cipher | Negotiated cipher suite | IANA name |
| cert_key_algorithm | Server certificate key | e.g. RSA-2048, ECDSA-secp256r1 |
| cert_signature_algorithm | Algorithm the CA used to sign the certificate | e.g. sha256WithRSAEncryption |
| cert_issuer | Issuing CA (organisation, else common name) | text |
| cert_not_after | Certificate expiry | YYYY-MM-DD |
| kex_quantum_vulnerable | Key exchange breakable by a large quantum computer | true / false |
| auth_quantum_vulnerable | Certificate key breakable by a large quantum computer. Today every public CA certificate is RSA or ECDSA | true / false |
| transcript_sha256 | SHA-256 of the recorded handshake output. This is evidence the handshake happened; no keys or traffic are recorded | 64-hex |
| error | Why an endpoint was unreachable | text |
