/** @jest-environment node */
import { GET } from '@/app/admin/social/accounts/platform-callback/route';
test('callback scrubs supported codes before messaging',async()=>{const response=GET(),html=await response.text();expect(response.headers.get('Referrer-Policy')).toBe('no-referrer');expect(response.headers.get('Cache-Control')).toBe('private, no-store');expect(html.indexOf('replaceState')).toBeLessThan(html.indexOf('postMessage'));expect(html).toContain("query.get('auth_code')");expect(html).toContain('auditgava-platform-callback');expect(html).not.toContain('https://');});
