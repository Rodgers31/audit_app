import { threadsConservativeLength, xWeightedLength } from '@/lib/socialPlatformCounters';

test.each([
  ['a'.repeat(280), 280], ['漢'.repeat(140), 280], ['cafe\u0301', 4], ['👨‍👩‍👧‍👦', 2],
  ['🙋🏽', 2], ['🇰🇪', 2], ['1️⃣', 2], ['©', 1], ['©️', 2], ['👨‍🎤'.repeat(140), 280],
  ['https://example.com/a/very/long/link', 23], ['(https://example.com/a)', 25],
  ['a https://example.com', 25], ['https://example.com/ends.', 24],
  ['a'.repeat(257) + 'https://example.com', 280],
  ['a'.repeat(258) + 'https://example.com', 281],
  ['漢'.repeat(141), 282], ['Approved caption\n\n#AuditGava\n\nhttps://example.com', 53],
])('X weighted length is Unicode/URL aware: %s', (text, length) => {
  expect(xWeightedLength(String(text))).toEqual({ length });
});

test.each(['example.com', 'https://user:pass@example.com', 'https://☃.com', '\ud800', '\udfff', '\uffff',
  'https://example.com:abc', 'https://example.com:0', 'https://example.com\\foo', 'https://%65xample.com',
  'https://example_.com', 'http://example', 'www.example.com', null, 1])('X unavailable shapes never claim a numeric count: %s', text => {
  const result = xWeightedLength(text as string);
  expect(result.length).toBeNull();
  expect(result.error).toMatch(/valid Unicode and explicit ASCII HTTP/);
});

test('repeated calls do not inherit the global emoji or URL regex cursor', () => {
  const text = '👨‍👩‍👧‍👦 https://example.com/report';
  for (let index = 0; index < 5; index++) expect(xWeightedLength(text)).toEqual({ length: 26 });
});

test.each([['a'.repeat(500), 500], ['a'.repeat(501), 501], ['漢', 3], ['😀', 4], ['cafe\u0301', 6],
  ['👨‍👩‍👧‍👦', 25]])('Threads conservative application budget uses transmitted UTF-8 bytes: %s', (text, length) => {
  expect(threadsConservativeLength(String(text))).toEqual({ length });
});

test.each(['\ud800', '\udfff', '\uffff', null, 1])('Threads malformed Unicode is unavailable: %s', text => {
  expect(threadsConservativeLength(text as string).length).toBeNull();
});
