package main

import "crypto/tls"

var cfg = &tls.Config{CurvePreferences: []tls.CurveID{tls.CurveP256}}
