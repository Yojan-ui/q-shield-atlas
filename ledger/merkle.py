"""RFC 6962 Merkle tree over ledger entries.

leaf = SHA256(0x00 || entry_bytes), node = SHA256(0x01 || left || right). MTH splits n leaves at
k = the largest power of two < n, which is the same tree as building level by level and
promoting (not duplicating) an odd last node. Inclusion proofs follow RFC 6962 2.1.1 (PATH) and
are verified with the RFC 9162 2.1.3.2 algorithm.
"""

import hashlib


def leaf_hash(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n: int) -> int:
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def _mth(leaves: list[bytes]) -> bytes:
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return leaves[0]
    k = _split(n)
    return node_hash(_mth(leaves[:k]), _mth(leaves[k:]))


def _path(m: int, leaves: list[bytes]) -> list[bytes]:
    n = len(leaves)
    if n <= 1:
        return []
    k = _split(n)
    if m < k:
        return _path(m, leaves[:k]) + [_mth(leaves[k:])]
    return _path(m - k, leaves[k:]) + [_mth(leaves[:k])]


class MerkleTree:
    def __init__(self, items: list[bytes]):
        self.leaves = [leaf_hash(x) for x in items]

    def root(self) -> str:
        return _mth(self.leaves).hex()

    def inclusion_proof(self, index: int) -> list[str]:
        if not 0 <= index < len(self.leaves):
            raise IndexError(index)
        return [h.hex() for h in _path(index, self.leaves)]


def verify_proof(item: bytes, index: int, tree_size: int, proof: list[str], root: str) -> bool:
    """RFC 9162 2.1.3.2 inclusion-proof verification."""
    if not 0 <= index < tree_size:
        return False
    fn, sn = index, tree_size - 1
    r = leaf_hash(item)
    for p in (bytes.fromhex(h) for h in proof):
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r.hex() == root
