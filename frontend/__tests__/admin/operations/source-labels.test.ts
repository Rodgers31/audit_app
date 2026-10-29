import {sourceLabel} from '@/lib/admin/sourceLabels';

test.each(['__proto__','constructor','toString','hasOwnProperty','valueOf'])('unregistered source %s always has a text label',domain=>{
  expect(typeof sourceLabel(domain)).toBe('string');
  expect(sourceLabel(domain)).toContain(domain.replaceAll('_',' '));
});
test('registered source labels retain their reporting scope',()=>{
  expect(sourceLabel('pending_bills')).toBe('County pending bills');
  expect(sourceLabel('revenue_by_source')).toBe('KRA revenue collections');
});
