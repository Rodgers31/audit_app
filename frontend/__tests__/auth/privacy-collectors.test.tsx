import { render } from '@testing-library/react';
import PrivacyCollectors from '@/components/PrivacyCollectors';
import { filterAuthEvent } from '@/lib/auth/privacy';
import NavTrailTracker from '@/lib/navigation/NavTrailTracker';
const mockAnalytics = jest.fn((_props: unknown) => null);
const mockSpeed = jest.fn((_props: unknown) => null);
let mockPath = '/';
let mockSearch = new URLSearchParams();
jest.mock('@vercel/analytics/react', () => ({ Analytics: (props: unknown) => mockAnalytics(props) }));
jest.mock('@vercel/speed-insights/next', () => ({ SpeedInsights: (props: unknown) => mockSpeed(props) }));
jest.mock('next/navigation', () => ({ usePathname: () => mockPath, useSearchParams: () => mockSearch }));
beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  mockSearch = new URLSearchParams();
  mockPath = '/';
});
test.each(['/reset-password', '/auth/callback', '/admin/social/accounts/callback', '/admin/social/accounts/platform-callback'])('private path %s mounts no collectors or trail entry', path => {
  mockPath = path;
  mockSearch = new URLSearchParams('code=INERT_MARKER');
  render(<><PrivacyCollectors /><NavTrailTracker /></>);
  expect(mockAnalytics).not.toHaveBeenCalled();
  expect(mockSpeed).not.toHaveBeenCalled();
  expect(sessionStorage.getItem('auditgava-nav-trail')).toBeNull();
});
test('public page remains collected and tracked', () => {
  mockPath = '/audits';
  render(<><PrivacyCollectors /><NavTrailTracker /></>);
  expect(mockAnalytics).toHaveBeenCalledTimes(1);
  expect(mockSpeed).toHaveBeenCalledTimes(1);
  expect(sessionStorage.getItem('auditgava-nav-trail')).toContain('/audits');
});
test.each(['/reset-password?recovery=INERT_MARKER', '/auth/callback?code=INERT_MARKER', '/?code=INERT_MARKER', '/?access_token=INERT_MARKER', '/#access_token=INERT_MARKER'])('a retained public-page collector drops %s', url => {
  expect(filterAuthEvent({ url })).toBeNull();
});
test('ordinary public event survives', () => {
  const event = { url: 'https://app.test/audits?year=2025' };
  expect(filterAuthEvent(event)).toBe(event);
});
