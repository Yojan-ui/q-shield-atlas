from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import jwt

SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
EPHEMERAL = ec.generate_private_key(ec.SECP256R1())
rsa_enabled = False  # decoy: a variable name is not crypto use


def token(claims):
    return jwt.encode(claims, SIGNING_KEY, algorithm="RS256")


def seal(key, nonce, data):
    return AESGCM(key).encrypt(nonce, data, None)  # decoy: symmetric AES is not quantum-broken
