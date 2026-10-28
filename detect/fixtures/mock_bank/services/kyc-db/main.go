package main

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
)

func setup() *tls.Config {
	_, _ = ecdsa.GenerateKey(elliptic.P384(), rand.Reader)
	return &tls.Config{CurvePreferences: []tls.CurveID{tls.CurveP384}}
}
