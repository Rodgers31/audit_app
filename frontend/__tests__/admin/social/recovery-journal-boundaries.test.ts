import { confirmSocialCommand, socialCommandKey } from '@/lib/api/socialCommandRecovery';
import { confirmUpload, recoverUpload, retainUpload } from '@/components/admin/social/media/uploadRecovery';
const actor = '00000000-0000-4000-8000-000000000001';
const key = '00000000-0000-4000-8000-000000000099';
const uploadKey = 'auditgava.social.uploads.v1:' + actor;
const commandKey = 'auditgava.social.commands.v1:' + actor;
const original = { identity: 'owned-fixture', initiateKey: key, completeKey: key, assetId: null, version: null, stored: false };
beforeEach(() => { sessionStorage.clear(); jest.restoreAllMocks(); });

test.each(['initiateKey', 'completeKey'] as const)('a retained array %s cannot authorize upload recovery', field => {
  sessionStorage.setItem(uploadKey, JSON.stringify({ version: 1, actor, entries: [{ ...original, [field]: [key] }] }));
  expect(() => recoverUpload(actor, original.identity)).toThrow();
});

test.each([{ label: 'empty', identity: '' }, { label: 'oversized', identity: 'x'.repeat(10001) }])('invalid new upload identity $label refuses before creating recovery state', ({ identity }) => {
  expect(() => recoverUpload(actor, identity)).toThrow();
  expect(sessionStorage.getItem(uploadKey)).toBeNull();
});

test.each(['', 'x'.repeat(2 * 1024 * 1024 + 1)])('invalid new command identity refuses before creating recovery state (%#)', identity => {
  expect(() => socialCommandKey(actor, identity)).toThrow();
  expect(sessionStorage.getItem(commandKey)).toBeNull();
});

test.each(['command', 'upload'])('an array actor cannot authorize a %s journal', kind => {
  const arrayActor = [actor] as unknown as string;
  expect(() => kind === 'command' ? socialCommandKey(arrayActor, 'owned-fixture') : recoverUpload(arrayActor, 'owned-fixture')).toThrow();
  expect(sessionStorage.length).toBe(0);
});

test.each(['command', 'upload'])('a full %s journal preserves existing recovery and refuses a new identity', kind => {
  const journalKey = kind === 'command' ? commandKey : uploadKey;
  const entries = Array.from({ length: 100 }, (_, n) => kind === 'command' ? { identity: 'owned-' + n, key } : { ...original, identity: 'owned-' + n });
  const raw = JSON.stringify({ version: 1, actor, entries }); sessionStorage.setItem(journalKey, raw);
  if (kind === 'command') { expect(socialCommandKey(actor, 'owned-1')).toBe(key); expect(() => socialCommandKey(actor, 'new-intent')).toThrow(); }
  else { expect(recoverUpload(actor, 'owned-1').initiateKey).toBe(key); expect(() => recoverUpload(actor, 'new-intent')).toThrow(); }
  expect(sessionStorage.getItem(journalKey)).toBe(raw);
});

test.each([
  { version: true }, { version: 2 }, { actor: key }, { entries: null }, { entries: {} },
  { entries: [{ ...original, stored: 1 }] }, { entries: [{ ...original, assetId: key, version: true }] },
  { entries: [{ ...original, assetId: key, version: -1 }] }, { entries: [{ ...original, extra: true }] },
  { entries: [original, original] },
])('malformed retained upload journal %# refuses and preserves its bytes', patch => {
  const raw = JSON.stringify({ version: 1, actor, entries: [original], ...patch }); sessionStorage.setItem(uploadKey, raw);
  expect(() => recoverUpload(actor, original.identity)).toThrow(); expect(sessionStorage.getItem(uploadKey)).toBe(raw);
});

test('a failed progress write does not lose the prior uncertain upload', () => {
  const entry = recoverUpload(actor, 'owned-fixture'); const prior = sessionStorage.getItem(uploadKey);
  jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage denied'); });
  expect(() => retainUpload(actor, { ...entry, assetId: key, version: 1 })).toThrow();
  expect(sessionStorage.getItem(uploadKey)).toBe(prior);
});

test('invalid progress cannot be persisted as a confirmed stored original', () => {
  const entry = recoverUpload(actor, 'owned-fixture'); const prior = sessionStorage.getItem(uploadKey);
  expect(() => retainUpload(actor, { ...entry, stored: true })).toThrow();
  expect(sessionStorage.getItem(uploadKey)).toBe(prior);
});

test('late confirmations cannot remove another command or upload identity', () => {
  const command = socialCommandKey(actor, 'owned-fixture'), upload = recoverUpload(actor, 'owned-fixture');
  confirmSocialCommand(actor, 'another-intent', command); confirmUpload(actor, { ...upload, identity: 'another-intent' });
  expect(socialCommandKey(actor, 'owned-fixture')).toBe(command); expect(recoverUpload(actor, 'owned-fixture')).toEqual(upload);
});
