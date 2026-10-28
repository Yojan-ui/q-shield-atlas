"""Generate the fictional mock-bank source tree scanned by detect/ (all names invented).

Each service has an owner-declared manifest `atlas-service.json` (name, kind, data class,
dependencies: facts a scanner cannot infer) plus config/code files whose crypto the scanner
must find. `status-page` only uses a hybrid PQC group and must not enter the migration inventory.
`web-gw` *claims* a hybrid group in config; the live lab server negotiates classical X25519,
which is the static-vs-live drift case.

python -m detect.fixtures.build_mock_bank
"""

import json
from pathlib import Path

from .make_fixture_certs import write as write_cert

ROOT = Path(__file__).parent / "mock_bank"

SERVICES = {
    "web-gw": ("Public web TLS gateway", "tls_gateway", "customer_pii", ["root-ca"], {
        "nginx.conf": "server {\n    listen 443 ssl;\n    ssl_certificate certs/web-gw.crt;\n"
                      "    ssl_ecdh_curve X25519MLKEM768:X25519;\n"
                      "    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA384;\n}\n",
    }),
    "cdn": ("Marketing CDN edge", "cdn_edge", "public_content", [], {
        "edge.conf": "server {\n    listen 443 ssl;\n    ssl_ecdh_curve prime256v1;\n}\n",
    }),
    "root-ca": ("Internal root CA", "root_ca", "regulatory_records", ["hsm"], {
        "openssl.cnf": "[ req ]\ndefault_bits = 4096\ndefault_md = sha256\n",
    }),
    "hsm": ("Payments HSM cluster", "hsm", "payments", [], {
        "hsm.properties": "partition=payments\nkey.wrap.mechanism=RSA_OAEP\nkey.size=RSA-2048\n",
    }),
    "auth": ("Auth / session service", "service_mtls", "auth_session", ["root-ca"], {
        "tokens.py": "from cryptography.hazmat.primitives.asymmetric import ec\nimport jwt\n\n"
                     "KEY = ec.generate_private_key(ec.SECP256R1())\n\n\n"
                     "def issue(claims):\n    return jwt.encode(claims, KEY, algorithm=\"ES256\")\n",
    }),
    "payments-api": ("Payments API", "service_mtls", "payments", ["hsm", "root-ca"], {
        "src/Signer.java": "import java.security.*;\n\npublic class Signer {\n    void init() throws Exception {\n"
                           "        KeyPairGenerator k = KeyPairGenerator.getInstance(\"RSA\");\n"
                           "        Signature s = Signature.getInstance(\"SHA256withRSA\");\n    }\n}\n",
    }),
    "ledger-db": ("Core ledger database link", "database_tls", "payments", ["root-ca"], {
        "postgresql.conf": "ssl = on\nssl_ciphers = 'ECDHE-RSA-AES256-GCM-SHA384'\nssl_min_protocol_version = 'TLSv1.2'\n",
    }),
    "kyc-db": ("KYC document store", "database_tls", "customer_pii", ["root-ca"], {
        "main.go": "package main\n\nimport (\n\t\"crypto/ecdsa\"\n\t\"crypto/elliptic\"\n\t\"crypto/rand\"\n\t\"crypto/tls\"\n)\n\n"
                   "func setup() *tls.Config {\n\t_, _ = ecdsa.GenerateKey(elliptic.P384(), rand.Reader)\n"
                   "\treturn &tls.Config{CurvePreferences: []tls.CurveID{tls.CurveP384}}\n}\n",
    }),
    "backup": ("Encrypted backup vault", "batch_sftp", "archive_backup", [], {
        "rotate-keys.sh": "#!/bin/sh\nset -e\nopenssl genrsa -out /vault/wrap.key 3072\n",
    }),
    "vpn": ("Branch site-to-site VPN", "vpn", "internal_ops", [], {
        "ipsec.conf": "conn branch\n    ike=aes256-sha256-ecp256\n    esp=aes256gcm16\n",
    }),
    "bus": ("Internal message bus", "message_bus", "trade_secrets", ["root-ca"], {
        "server.properties": "listeners=SSL://:9093\nssl.cipher.suites=ECDHE-RSA-AES128-GCM-SHA256\n",
    }),
    "sftp-reg": ("Regulator SFTP drop", "batch_sftp", "regulatory_records", [], {
        "sshd_config": "HostKey /etc/ssh/ssh_host_rsa_key\nKexAlgorithms diffie-hellman-group14-sha256\n",
    }),
    "crm": ("CRM integration", "service_mtls", "customer_pii", ["bus"], {
        "client.js": "const crypto = require('crypto');\nconst jwt = require('jsonwebtoken');\n\n"
                     "const { privateKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });\n"
                     "const token = jwt.sign(claims, privateKey, { algorithm: 'RS256' });\n",
    }),
    "risk-engine": ("Risk model service", "service_mtls", "trade_secrets", ["bus"], {
        "tls.go": "package main\n\nimport \"crypto/tls\"\n\nvar cfg = &tls.Config{CurvePreferences: []tls.CurveID{tls.CurveP256}}\n",
    }),
    "statements": ("Statement archive export", "batch_sftp", "archive_backup", ["backup"], {
        "export.sh": "#!/bin/sh\ngpg --batch --default-new-key-algo rsa2048 --quick-generate-key statements@bank.test\n",
    }),
    "ops-dash": ("Ops dashboard", "tls_gateway", "internal_ops", ["root-ca"], {
        "nginx.conf": "server {\n    listen 443 ssl;\n    ssl_ecdh_curve X25519;\n}\n",
    }),
    "status-page": ("Public status page (already hybrid PQC)", "tls_gateway", "public_content", [], {
        "nginx.conf": "server {\n    listen 443 ssl;\n    ssl_ecdh_curve X25519MLKEM768;\n}\n",
    }),
}


def main():
    from cryptography.hazmat.primitives.asymmetric import rsa

    for sid, (name, kind, data_class, deps, files) in SERVICES.items():
        d = ROOT / "services" / sid
        d.mkdir(parents=True, exist_ok=True)
        manifest = {"id": sid, "name": name, "kind": kind, "data_class": data_class, "depends_on": deps}
        (d / "atlas-service.json").write_text(json.dumps(manifest, indent=1) + "\n")
        for rel, text in files.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(text)
    write_cert(ROOT / "services" / "web-gw" / "certs" / "web-gw.crt", rsa.generate_private_key(public_exponent=65537, key_size=2048), "www.mockbank.test")
    write_cert(ROOT / "services" / "root-ca" / "certs" / "root-ca.crt", rsa.generate_private_key(public_exponent=65537, key_size=4096), "MockBank Root CA")
    (ROOT / "README.md").write_text("Fictional mock bank generated by detect/fixtures/build_mock_bank.py. Not real code.\n")


if __name__ == "__main__":
    main()
