const crypto = require('crypto');
const jwt = require('jsonwebtoken');

const { privateKey } = crypto.generateKeyPairSync('ec', { namedCurve: 'P-256' });
const wrapped = crypto.publicEncrypt(partnerKey, sessionKey);
const t = jwt.sign(payload, privateKey, { algorithm: 'ES256' });
const h = crypto.createHash('sha256'); // decoy
