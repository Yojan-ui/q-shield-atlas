"""Write the public test certificates used by scanner fixtures (private keys are discarded).

python -m detect.fixtures.make_fixture_certs
"""

import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

HERE = Path(__file__).parent


def self_signed(key, cn: str) -> bytes:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


def write(path: Path, key, cn: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(self_signed(key, cn))


def main():
    certs = HERE / "sample_services" / "gateway" / "certs"
    write(certs / "server.crt", rsa.generate_private_key(public_exponent=65537, key_size=2048), "gateway.sample.test")
    write(certs / "edge-ec.crt", ec.generate_private_key(ec.SECP256R1()), "edge.sample.test")


if __name__ == "__main__":
    main()
