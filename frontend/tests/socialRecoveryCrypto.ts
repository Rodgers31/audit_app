/** jsdom lacks the secure-browser digest API used to identify original bytes. */
import { webcrypto } from 'node:crypto';
Object.defineProperty(crypto, 'subtle', { configurable: true, value: {
  digest: (algorithm: string, bytes: ArrayBuffer) => webcrypto.subtle.digest(algorithm, Buffer.from(new Uint8Array(bytes))),
} });
