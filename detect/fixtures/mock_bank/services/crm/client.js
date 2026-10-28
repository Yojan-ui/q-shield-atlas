const crypto = require('crypto');
const jwt = require('jsonwebtoken');

const { privateKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
const token = jwt.sign(claims, privateKey, { algorithm: 'RS256' });
