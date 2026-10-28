"""Static detection rules for quantum-vulnerable public-key crypto (RSA, ECC, DH, DSA).

Each rule is a regex applied line by line to files matching its globs. `family` is what a CRQC
would break; `use` is kex (key establishment), sig (signatures/auth) or both. Rules with
family "PQC" mark post-quantum or hybrid usage (a positive finding, not a vulnerability).
"""

import re
from dataclasses import dataclass

CODE = ("*.py", "*.go", "*.java", "*.kt", "*.js", "*.ts", "*.mjs", "*.cs", "*.rb", "*.rs", "*.c", "*.cc", "*.cpp", "*.h", "*.php", "*.swift", "*.scala")
CONFIG = ("*.conf", "*.cnf", "*.cfg", "*.ini", "*.yaml", "*.yml", "*.json", "*.toml", "*.properties", "*.env", "Dockerfile", "*.tf", "*.xml", "*.sh", "nginx*", "sshd_config", "ssh_config", "*.service")
ANY = CODE + CONFIG
DEPS = ("requirements*.txt", "requirements*.in", "Pipfile", "pyproject.toml", "package.json", "go.mod", "pom.xml", "build.gradle", "*.csproj", "Gemfile", "Cargo.toml")


@dataclass(frozen=True)
class Rule:
    id: str
    family: str  # RSA | ECC | DH | DSA | PQC
    use: str  # kex | sig | both
    pattern: re.Pattern
    globs: tuple[str, ...]
    description: str
    confidence: str = "high"
    unless_next: re.Pattern | None = None  # skip the hit if the next non-blank line matches


def _r(id, family, use, regex, globs, description, confidence="high", flags=0, unless_next=None):
    return Rule(id, family, use, re.compile(regex, flags), globs, description, confidence,
                re.compile(unless_next) if unless_next else None)


I = re.IGNORECASE
RULES: tuple[Rule, ...] = (
    # ---- Python ----
    _r("py-rsa-generate", "RSA", "both", r"\brsa\.generate_private_key\s*\(", ("*.py",), "cryptography RSA key generation"),
    _r("py-rsa-pycryptodome", "RSA", "both", r"\bRSA\.(generate|import_key|importKey)\s*\(", ("*.py",), "PyCryptodome RSA key"),
    _r("py-ec-generate", "ECC", "both", r"\bec\.generate_private_key\s*\(", ("*.py",), "cryptography EC key generation"),
    _r("py-ec-curve", "ECC", "both", r"\bec\.(SECP256R1|SECP384R1|SECP521R1|SECP256K1)\b", ("*.py",), "cryptography named EC curve"),
    _r("py-x25519", "ECC", "kex", r"\b(X25519PrivateKey|X448PrivateKey)\b", ("*.py",), "cryptography X25519/X448 key agreement"),
    _r("py-ed25519", "ECC", "sig", r"\b(Ed25519PrivateKey|Ed448PrivateKey)\b", ("*.py",), "cryptography EdDSA signing key"),
    _r("py-dh", "DH", "kex", r"\bdh\.generate_parameters\s*\(", ("*.py",), "finite-field Diffie-Hellman"),
    _r("py-paramiko-rsa", "RSA", "sig", r"\bparamiko\.RSAKey\b", ("*.py",), "Paramiko RSA SSH key"),
    # ---- Go ----
    _r("go-rsa", "RSA", "both", r"\brsa\.(GenerateKey|EncryptOAEP|EncryptPKCS1v15|SignPKCS1v15|SignPSS)\s*\(", ("*.go",), "Go crypto/rsa"),
    _r("go-ecdsa", "ECC", "sig", r"\becdsa\.(GenerateKey|Sign|SignASN1)\s*\(", ("*.go",), "Go crypto/ecdsa"),
    _r("go-elliptic", "ECC", "both", r"\belliptic\.(P224|P256|P384|P521)\s*\(", ("*.go",), "Go elliptic curve"),
    _r("go-ecdh", "ECC", "kex", r"\becdh\.(P256|P384|P521|X25519)\s*\(", ("*.go",), "Go crypto/ecdh"),
    _r("go-tls-curves", "ECC", "kex", r"\btls\.(CurveP256|CurveP384|CurveP521|X25519)\b", ("*.go",), "Go TLS classical curve preference"),
    _r("go-tls-mlkem", "PQC", "kex", r"\btls\.(X25519MLKEM768|X25519Kyber768Draft00)\b", ("*.go",), "Go TLS hybrid ML-KEM group"),
    # ---- Java / Kotlin ----
    _r("java-kpg", "RSA", "both", r"KeyPairGenerator\.getInstance\(\s*\"RSA\"", ("*.java", "*.kt"), "JCA RSA key pair"),
    _r("java-kpg-ec", "ECC", "both", r"KeyPairGenerator\.getInstance\(\s*\"(EC|ECDSA|XDH|X25519|Ed25519)\"", ("*.java", "*.kt"), "JCA EC key pair"),
    _r("java-sig", "RSA", "sig", r"Signature\.getInstance\(\s*\"\w*with(RSA|RSA/PSS)\"", ("*.java", "*.kt"), "JCA RSA signature"),
    _r("java-sig-ec", "ECC", "sig", r"Signature\.getInstance\(\s*\"\w*withECDSA\"", ("*.java", "*.kt"), "JCA ECDSA signature"),
    _r("java-cipher-rsa", "RSA", "kex", r"Cipher\.getInstance\(\s*\"RSA", ("*.java", "*.kt"), "JCA RSA encryption"),
    _r("java-ka", "ECC", "kex", r"KeyAgreement\.getInstance\(\s*\"(ECDH|DH|XDH|X25519)\"", ("*.java", "*.kt"), "JCA key agreement"),
    # ---- JavaScript / TypeScript ----
    _r("node-keypair", "RSA", "both", r"generateKeyPair(Sync)?\(\s*['\"](rsa|rsa-pss)['\"]", ("*.js", "*.ts", "*.mjs"), "Node crypto RSA key pair"),
    _r("node-keypair-ec", "ECC", "both", r"generateKeyPair(Sync)?\(\s*['\"](ec|ed25519|ed448|x25519|x448)['\"]", ("*.js", "*.ts", "*.mjs"), "Node crypto EC key pair"),
    _r("node-ecdh", "ECC", "kex", r"\bcreateECDH\s*\(", ("*.js", "*.ts", "*.mjs"), "Node ECDH"),
    _r("node-rsa-encrypt", "RSA", "kex", r"\bpublicEncrypt\s*\(", ("*.js", "*.ts", "*.mjs"), "Node RSA public-key encryption"),
    # ---- C# ----
    _r("cs-rsa", "RSA", "both", r"\b(RSA\.Create|RSACryptoServiceProvider|new\s+RSACng)\b", ("*.cs",), ".NET RSA"),
    _r("cs-ecdsa", "ECC", "both", r"\b(ECDsa\.Create|ECDiffieHellman\.Create)\b", ("*.cs",), ".NET ECC"),
    # ---- JWT / token algorithms (code or config) ----
    _r("jwt-rs", "RSA", "sig", r"[\"'](RS256|RS384|RS512|PS256|PS384|PS512)[\"']", ANY, "JWT RSA signature algorithm"),
    _r("jwt-es", "ECC", "sig", r"[\"'](ES256|ES384|ES512|EdDSA)[\"']", ANY, "JWT ECDSA/EdDSA signature algorithm"),
    # ---- TLS / web server config ----
    _r("nginx-ecdh-curve", "ECC", "kex", r"^\s*ssl_ecdh_curve\s+[^;]*\b(prime256v1|secp384r1|secp521r1|X25519|X448|P-256|P-384)\b", CONFIG, "nginx classical ECDH groups"),
    _r("tls-groups-pqc", "PQC", "kex", r"\b(X25519MLKEM768|SecP256r1MLKEM768|SecP384r1MLKEM1024|MLKEM768|MLKEM1024)\b", ANY, "hybrid / ML-KEM TLS group configured"),
    _r("tls-ciphers-ecdhe-rsa", "RSA", "sig", r"\b(ECDHE|DHE)-RSA-[A-Z0-9-]+", CONFIG, "TLS 1.2 suite with RSA authentication", "medium"),
    _r("tls-ciphers-ecdhe", "ECC", "kex", r"\bECDHE-(RSA|ECDSA)-[A-Z0-9-]+", CONFIG, "TLS 1.2 suite with ECDHE key exchange", "medium"),
    _r("tls-ciphers-rsa-kex", "RSA", "kex", r"(?<![-\w])(AES(128|256)-(GCM-)?SHA(256|384)?|RSA-AES|TLS_RSA_WITH_\w+)\b", CONFIG, "TLS static-RSA key exchange suite"),
    _r("openssl-default-bits", "RSA", "both", r"^\s*default_bits\s*=\s*\d+", ("*.cnf", "*.conf", "*.cfg"), "OpenSSL req RSA key size"),
    _r("openssl-cli-rsa", "RSA", "both", r"\bopenssl\s+(genrsa|req\b[^\n]*-newkey\s+rsa:\d+|genpkey\b[^\n]*-algorithm\s+RSA)", ANY, "OpenSSL CLI RSA key generation", flags=I),
    _r("openssl-cli-ec", "ECC", "both", r"\bopenssl\s+(ecparam|genpkey\b[^\n]*-algorithm\s+(EC|ED25519|X25519))", ANY, "OpenSSL CLI EC key generation", flags=I),
    _r("ssh-keytype", "RSA", "sig", r"\b(ssh-rsa|rsa-sha2-256|rsa-sha2-512|ssh-keygen\s+[^\n]*-t\s+rsa)\b", ANY, "SSH RSA host/user key"),
    _r("ssh-keytype-ec", "ECC", "sig", r"\b(ecdsa-sha2-nistp\d+|ssh-ed25519|ssh-keygen\s+[^\n]*-t\s+(ecdsa|ed25519))\b", ANY, "SSH ECC host/user key"),
    _r("ssh-hostkey-file", "RSA", "sig", r"\bssh_host_(rsa|dsa)_key\b", ANY, "SSH RSA/DSA host key file"),
    _r("ssh-hostkey-file-ec", "ECC", "sig", r"\bssh_host_(ecdsa|ed25519)_key\b", ANY, "SSH ECC host key file"),
    _r("ssh-kex", "ECC", "kex", r"^\s*KexAlgorithms\s+[^\n]*\b(curve25519-sha256|ecdh-sha2-nistp\d+)", CONFIG, "SSH elliptic-curve key exchange"),
    _r("ssh-kex-dh", "DH", "kex", r"^\s*KexAlgorithms\s+[^\n]*\bdiffie-hellman-group[\w-]*", CONFIG, "SSH finite-field DH key exchange"),
    _r("ssh-kex-pqc", "PQC", "kex", r"\b(sntrup761x25519-sha512|mlkem768x25519-sha256)\b", ANY, "SSH post-quantum hybrid key exchange"),
    _r("ipsec-ecdh", "ECC", "kex", r"\b(ecp256|ecp384|ecp521|curve25519)\b(?!-sha)", CONFIG, "IKE/IPsec elliptic-curve DH group"),
    _r("ipsec-modp", "DH", "kex", r"\bmodp(1024|1536|2048|3072|4096|6144|8192)\b", CONFIG, "IKE/IPsec finite-field DH group"),
    _r("pgp-rsa", "RSA", "both", r"\b(Key-Type|key-type)\s*:\s*RSA\b|--default-new-key-algo\s+rsa", ANY, "OpenPGP RSA key"),
    _r("key-wrap-rsa", "RSA", "kex", r"\bRSA[-_]?OAEP\b|\bRSA[-_](2048|3072|4096)\b", CONFIG, "RSA key wrapping / RSA key size in config", "medium"),
    # ---- dependency manifests: libraries whose purpose is classical public-key crypto ----
    _r("dep-python-rsa", "RSA", "both", r"^\s*rsa\s*(==|>=|~=|<=|>|<|$)", ("requirements*.txt", "requirements*.in", "Pipfile"), "python-rsa library dependency", "medium"),
    _r("dep-python-ecdsa", "ECC", "sig", r"^\s*ecdsa\s*(==|>=|~=|<=|>|<|$)", ("requirements*.txt", "requirements*.in", "Pipfile"), "python-ecdsa library dependency", "medium"),
    _r("dep-node-rsa", "RSA", "both", r"\"(node-rsa|node-forge)\"\s*:", ("package.json",), "Node RSA library dependency", "medium"),
    _r("dep-node-elliptic", "ECC", "both", r"\"(elliptic|secp256k1)\"\s*:", ("package.json",), "Node elliptic-curve library dependency", "medium"),
    # ---- TLS on library defaults: group chosen at runtime, so static analysis cannot decide ----
    _r("tls-default-go", "UNKNOWN", "kex", r"(?<![*\w.])&?tls\.Config\{(?![^\n]*CurvePreferences)", ("*.go",), "Go TLS config; key-exchange group set by Go defaults at runtime - verify with a live probe", "low"),
    _r("tls-default-yaml", "UNKNOWN", "kex", r"^\s*tls:\s*(\{\s*\}|#.*)?$", ("*.yaml", "*.yml"), "TLS block on library defaults - verify with a live probe", "low",
       unless_next=r"^\s*insecure:\s*true\b"),  # OTel-style `insecure: true` turns TLS off
    _r("tls-default-python", "UNKNOWN", "kex", r"\bssl\.(create_default_context|SSLContext)\s*\(|\bsslopt\s*=", ("*.py",), "Python TLS context on defaults - verify with a live probe", "low"),
    # ---- PEM headers (any text file) ----
    _r("pem-rsa-private", "RSA", "both", r"-----BEGIN RSA PRIVATE KEY-----", ANY + ("*.pem", "*.key"), "PEM RSA private key (contents not read)"),
    _r("pem-ec-private", "ECC", "both", r"-----BEGIN EC PRIVATE KEY-----", ANY + ("*.pem", "*.key"), "PEM EC private key (contents not read)"),
    _r("pem-ssh-private", "RSA", "sig", r"-----BEGIN OPENSSH PRIVATE KEY-----", ANY + ("*.pem", "*.key"), "OpenSSH private key (type not read)", "low"),
)
