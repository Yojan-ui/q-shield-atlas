# detect/ on real open-source microservice repos: manual review

Scanned read-only at the commits pinned in `detect/real_repos.json`; regenerate with
`python -m detect.real_repos` (writes `out/real_repos/<name>.json` with run_id and timestamp).
Review done 2026-10-28 by reading every finding and an independent case-insensitive grep for
crypto terms (rsa, ecdsa, ecdh, x509, tls, jwt, ssl_, curve names, PEM headers).

## Online Boutique (GoogleCloudPlatform/microservices-demo @ c7cb6d5bfd6e)

| finding | verdict |
|---|---|
| `src/{emailservice,recommendationservice,shoppingassistantservice}/requirements.txt`, `recommendationservice/requirements.in`: `rsa==4.9[.1]` | correct: python-rsa dependency (pulled in by google-auth) |
| `helm-chart/templates/cartservice.yaml:382` `tls:` (Istio `mode: SIMPLE`) | correct: TLS on platform defaults, needs live probe |

Not visible to a static scan: the GCP load-balancer SSL policy (created by `gcloud` in a README)
and Istio mesh mTLS defaults. Those are exactly the cases the live probe is for.

## OpenTelemetry Demo (open-telemetry/opentelemetry-demo @ 841adc0194e9)

| finding | verdict |
|---|---|
| `src/chatbot/src/opamp.py:101` `sslopt=` | correct: Python TLS on defaults |
| `src/otel-collector/otelcol-config-observability.yml:51` `tls:` + `insecure_skip_verify: true` | correct: TLS on (unverified) |
| `src/product-catalog/opamp.go:147` `&tls.Config{InsecureSkipVerify: true}` | correct: Go TLS on defaults |

## Errors found and fixed during review

- **Missed:** dependency manifests were not scanned. Added `dep-*` rules (python-rsa, python-ecdsa,
  node-rsa/node-forge, elliptic/secp256k1).
- **Missed:** TLS left on library defaults was invisible. Added low-confidence `UNKNOWN` rules
  ("needs live probe"); these are not counted as vulnerable.
- **False positives (6):** OTel collector `tls:` blocks followed by `insecure: true` (TLS disabled,
  i.e. plaintext) were first reported as TLS-on-defaults. Rules can now veto a hit on the next
  non-blank line (`unless_next`); a decoy for this case is in the sample-services fixture.
- **False positive:** a Go function signature returning `*tls.Config` matched the TLS rule;
  the rule now needs a literal `tls.Config{` and skips configs that set `CurvePreferences`.

## Known remaining gaps

- `src/frontend/pages/_app.tsx:50` `tls: useTLS` (a JS client option) is not flagged.
- Plaintext links (`insecure: true`) are a bigger harvest-now-decrypt-later risk than classical
  TLS but are out of scope for an RSA/ECC detector; they are not reported.
- Neither repo implements asymmetric crypto in its own code, so these repos exercise the
  dependency and TLS-default rules, not the code rules. Code rules are covered by the
  hand-labelled `detect/fixtures/sample_services` ground truth.
