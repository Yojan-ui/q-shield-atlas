from cryptography.hazmat.primitives.asymmetric import ec
import jwt

KEY = ec.generate_private_key(ec.SECP256R1())


def issue(claims):
    return jwt.encode(claims, KEY, algorithm="ES256")
