'use strict';
// Retain exact signed originals without publishing replayable request credentials.
const crypto = require('node:crypto');
const fs = require('node:fs');
const SCHEMA = 'nightly-refresh-sealed-evidence-v1';
const LIMIT = 131072;
const fields = ['schema','algorithm','nonce','ciphertext','tag','plaintext_sha256'];
function requireValue(value) { if (!value) throw new Error('evidence_refused'); }
function key(secret) {
  requireValue(typeof secret === 'string' && secret.length > 0 && Buffer.byteLength(secret) <= 65536);
  return crypto.createHmac('sha256', secret).update('auditgava:nightly-refresh-evidence:v1').digest();
}
function decode(value, maximum) {
  requireValue(typeof value === 'string' && value.length <= Math.ceil(maximum/3)*4);
  const bytes=Buffer.from(value,'base64');
  requireValue(bytes.length>0 && bytes.length<=maximum && bytes.toString('base64')===value);
  return bytes;
}
function seal(raw, secret) {
  requireValue(Buffer.isBuffer(raw) && raw.length>0 && raw.length<=LIMIT);
  const nonce=crypto.randomBytes(12), cipher=crypto.createCipheriv('aes-256-gcm',key(secret),nonce,{authTagLength:16});
  cipher.setAAD(Buffer.from(SCHEMA));
  const ciphertext=Buffer.concat([cipher.update(raw),cipher.final()]);
  return {schema:SCHEMA,algorithm:'aes-256-gcm',nonce:nonce.toString('base64'),ciphertext:ciphertext.toString('base64'),
    tag:cipher.getAuthTag().toString('base64'),plaintext_sha256:crypto.createHash('sha256').update(raw).digest('hex')};
}
function open(envelope, secret) {
  requireValue(envelope!==null && typeof envelope==='object' && !Array.isArray(envelope) &&
    Object.keys(envelope).sort().join('|')===fields.slice().sort().join('|') && envelope.schema===SCHEMA &&
    envelope.algorithm==='aes-256-gcm' && typeof envelope.plaintext_sha256==='string' && /^[a-f0-9]{64}$/.test(envelope.plaintext_sha256));
  const nonce=decode(envelope.nonce,12), tag=decode(envelope.tag,16), ciphertext=decode(envelope.ciphertext,LIMIT);
  requireValue(nonce.length===12 && tag.length===16);
  const decipher=crypto.createDecipheriv('aes-256-gcm',key(secret),nonce,{authTagLength:16});
  decipher.setAAD(Buffer.from(SCHEMA));decipher.setAuthTag(tag);
  const raw=Buffer.concat([decipher.update(ciphertext),decipher.final()]);
  requireValue(crypto.createHash('sha256').update(raw).digest('hex')===envelope.plaintext_sha256);
  return raw;
}
module.exports={seal,open};
if (require.main===module) {
  try {
    const mode=process.argv[2];requireValue(['seal','open'].includes(mode) && process.argv.length===3);
    const chunks=[];let size=0;
    while (true) {
      const chunk=Buffer.alloc(16384), count=fs.readSync(0,chunk,0,chunk.length,null);
      if (!count) break;
      size+=count;requireValue(size<=(mode==='seal'?LIMIT:196608));chunks.push(chunk.subarray(0,count));
    }
    const raw=Buffer.concat(chunks), secret=process.env.REVALIDATE_SECRET;
    process.stdout.write(mode==='seal'?JSON.stringify(seal(raw,secret)):open(JSON.parse(raw.toString('utf8')),secret));
  } catch {
    process.stderr.write('Evidence encryption or verification refused.\n');process.exitCode=1;
  }
}
