/** Export actual component markup for the isolated responsive browser check. */
import { mkdirSync, readFileSync, writeFileSync } from 'fs';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import MediaPicker from '@/components/admin/social/media/MediaPicker';
import MediaUpload from '@/components/admin/social/media/MediaUpload';
import { mediaKeys } from '@/lib/hooks/useSocialMedia';
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
const actor='00000000-0000-4000-8000-000000000001';
test('export actual media controls for responsive fixture verification', async () => {
  if (!process.env.SOCIAL_MEDIA_VISUAL_EXPORT) return;
  mkdirSync('.media-preview',{ recursive:true });
  const qc=new QueryClient({ defaultOptions:{ queries:{ retry:false } } });
  qc.setQueryData([...mediaKeys.root(actor),'library',{ page:1,q:'',kind:'' }],{ assets:[{ id:actor,version:2,filename:'Budget-review-original-photograph.png',state:'ready',mime_type:'image/png',byte_size:123456,sha256:'a'.repeat(64),width:1920,height:1080,duration_ms:null,default_alt_text:'An evidence document',safe_error:null,created_at:new Date().toISOString() }],total:1,page:1,page_size:20,has_more:false });
  const style=readFileSync('components/admin/social/media/media.module.css','utf8');
  function save(name:string,markup:string) { writeFileSync(`.media-preview/${name}.html`,`<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{margin:16px;font:14px/1.6 Arial,sans-serif;background:#f5f2e8;color:#1d3025}main{max-width:760px;margin:auto}*{box-sizing:border-box}${style}</style></head><body><main>${markup}</main></body></html>`); }
  const tree=render(<QueryClientProvider client={qc}><MediaPicker selected={[]} onSelect={jest.fn()} onClose={jest.fn()} /></QueryClientProvider>);
  await screen.findByRole('button',{ name:'Use Budget-review-original-photograph.png' }); save('library',tree.container.innerHTML); tree.unmount();
  const upload=render(<QueryClientProvider client={qc}><MediaUpload capabilities={{ upload_available:true,library_available:true,allowed_mime_types:['image/jpeg','image/png','video/mp4'],max_image_bytes:10485760,max_video_bytes:52428800,unavailable_reason:null }} onSelect={jest.fn()} onClose={jest.fn()} onBusy={jest.fn()} contextKey='visual-fixture' /></QueryClientProvider>);
  save('upload',upload.container.innerHTML);
});
