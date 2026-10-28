package main

import (
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/tls"
)

func keys() {
	_, _ = rsa.GenerateKey(rand.Reader, 3072)
	_ = elliptic.P256()
	_ = sha256.Sum256([]byte("decoy: hashing is fine"))
}

func tlsConfig() *tls.Config {
	return &tls.Config{CurvePreferences: []tls.CurveID{tls.X25519MLKEM768, tls.CurveP256}}
}
