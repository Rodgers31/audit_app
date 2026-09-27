import { MESSAGES } from '@/lib/i18n/messages';

it('describes modified opinions without implying an institution is bad or unaudited', () => {
  expect(MESSAGES['home.audits.adverse'].plain).toBe('Accounts materially misstated');
  expect(MESSAGES['home.audits.disclaimer'].plain).toBe('Insufficient evidence for an opinion');
  expect(MESSAGES['home.audits.qualified'].plain).toBe('Opinion with specific exceptions');
  expect(MESSAGES['home.audits.qualified'].sw).toBe('Qualified opinion');
  expect(MESSAGES['home.audits.adverse'].sw).toBe('Adverse opinion');
});
