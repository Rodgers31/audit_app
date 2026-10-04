/** @jest-environment node */
import { createHash } from 'node:crypto';
import { runInNewContext } from 'node:vm';
import { GET } from '@/app/admin/social/accounts/callback/route';

test('standalone callback scrubs query before communicating and has no tracking resources', async () => {
  const response=GET(), html=await response.text();
  expect(response.headers.get('cache-control')).toBe('private, no-store');
  expect(response.headers.get('referrer-policy')).toBe('no-referrer');
  const script=html.match(/<script>([\s\S]*?)<\/script>/)![1];
  const hash=createHash('sha256').update(script).digest('base64');
  expect(response.headers.get('content-security-policy')).toContain(`script-src 'sha256-${hash}'`);
  expect(html).not.toMatch(/src=|analytics|facebook\.com|supabase/);
  const calls: string[]=[];
  const origin='https://admin.example.test', pathname='/admin/social/accounts/callback';
  runInNewContext(script,{ URLSearchParams, document:{getElementById:()=>({textContent:''})},window:{location:{search:'?code=short-code&state=flow-state',pathname,origin},history:{replaceState:(_a:unknown,_b:unknown,url:string)=>{expect(url).toBe(pathname);calls.push('scrub');}},opener:{postMessage:(value:unknown,to:string)=>{expect(to).toBe(origin);expect(value).toEqual({type:'auditgava-meta-callback',code:'short-code',state:'flow-state',denied:false});calls.push('message');}},close:()=>calls.push('close')}});
  expect(calls).toEqual(['scrub','message','close']);
});
