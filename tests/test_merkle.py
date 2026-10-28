import hashlib
import random

import pytest

from ledger.merkle import MerkleTree, leaf_hash, node_hash, verify_proof

# Certificate Transparency reference vectors (RFC 6962 test data used by CT implementations).
CT_LEAVES = [b"", b"\x00", b"\x10", b"\x20\x21", b"\x30\x31", b"\x40\x41\x42\x43",
             b"\x50\x51\x52\x53\x54\x55\x56\x57", bytes(range(0x60, 0x70))]
CT_ROOTS = [
    "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
    "fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125",
    "aeb6bcfe274b70a14fb067a5e5578264db0fa9b51af5e0ba159158f329e06e77",
    "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7",
    "4e3bbb1f7b478dcfe71fb631631519a3bca12c9aefca1612bfce4c13a86264d4",
    "76e67dadbcdf1e10e1b74ddc608abd2f98dfb16fbce75277b5232a127f2087ef",
    "ddb89be403809e325750d3d263cd78929c2942b7942a34b77e122c9594a74c8c",
    "5dc9da79a70659a9ad559cb701ded9a2ab9d823aad2f4960cfe370eff4604328",
]


@pytest.mark.parametrize("n", range(1, 9))
def test_ct_reference_roots(n):
    assert MerkleTree(CT_LEAVES[:n]).root() == CT_ROOTS[n - 1]


def test_empty_tree_root():
    assert MerkleTree([]).root() == hashlib.sha256(b"").hexdigest()


def promote_odd_root(items):
    """Independent level-by-level build: pair up, promote an odd last node unchanged."""
    level = [leaf_hash(x) for x in items]
    while len(level) > 1:
        nxt = [node_hash(level[i], level[i + 1]) for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0].hex()


@pytest.mark.parametrize("n", range(1, 40))
def test_root_equals_promote_odd_construction(n):
    items = [f"entry-{i}".encode() for i in range(n)]
    assert MerkleTree(items).root() == promote_odd_root(items)


@pytest.mark.parametrize("n", [1, 2, 3, 5, 7, 8, 13, 31])
def test_every_inclusion_proof_verifies_and_rejects_tampering(n):
    items = [f"entry-{i}".encode() for i in range(n)]
    tree = MerkleTree(items)
    root = tree.root()
    for i in range(n):
        proof = tree.inclusion_proof(i)
        assert verify_proof(items[i], i, n, proof, root)
        assert not verify_proof(items[i] + b"x", i, n, proof, root)
        if n > 1:
            assert not verify_proof(items[i], (i + 1) % n, n, proof, root)
        if proof:
            bad = list(proof)
            bad[0] = "00" * 32
            assert not verify_proof(items[i], i, n, bad, root)


def test_random_proof():
    rng = random.Random(7)
    items = [rng.randbytes(40) for _ in range(23)]
    tree = MerkleTree(items)
    i = rng.randrange(23)
    assert verify_proof(items[i], i, 23, tree.inclusion_proof(i), tree.root())
