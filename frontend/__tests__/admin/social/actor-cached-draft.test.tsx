import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import AdminLayout from '@/app/admin/layout';
import {SocialEditorPage} from '@/components/admin/social/SocialWorkspace';
import {socialKeys} from '@/lib/hooks/useSocial';
import api from '@/lib/api/axios';
import {accounts,actorId,post,system,validation} from '@/tests/socialFixtures';
let actor=actorId;
jest.mock('@/lib/auth/AuthProvider',()=>({useAuth:()=>({user:{id:actor,roles:['admin']},authUser:{id:actor},isAuthenticated:true,isLoading:false})}));
jest.mock('@/lib/api/axios',()=>({__esModule:true,default:{get:jest.fn(),post:jest.fn(),patch:jest.fn()}}));
jest.mock('next/navigation',()=>({usePathname:()=>'/admin/social/owned',useRouter:()=>({push:jest.fn(),replace:jest.fn()})}));
jest.mock('@/components/admin/social/GeneratedEvidence',()=>({__esModule:true,default:()=>null}));
test('verified admin actor change retires prior local caption even when next actor has cached authorized detail',async()=>{
 const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
 const initial=post({origin_type:'generated',editorial_state:'pending_review',document:{...post().document,master:{...post().document.master,text:'Saved public fixture caption',link:'https://www.auditgava.com/budget'}}});
 const other='00000000-0000-4000-8000-000000000099';
 const loaded=post({...initial,document:{...initial.document,master:{...initial.document.master,text:'B authorized saved caption'}}});
 (api.get as jest.Mock).mockImplementation(async(path:string)=>({data:path.endsWith('/accounts')?{accounts}:path.endsWith('/system/status')?{...system,publishing_enabled:false}:path.endsWith('/media/capabilities')?{upload_available:false,library_available:false,allowed_mime_types:[],max_image_bytes:10485760,max_video_bytes:52428800,unavailable_reason:'Owned disabled media'}:actor===actorId?initial:loaded}));
 (api.post as jest.Mock).mockResolvedValue({data:validation(initial)});
 client.setQueryData(socialKeys.detail(actorId,initial.id),initial);
 const view=()=> <QueryClientProvider client={client}><AdminLayout><SocialEditorPage postId={initial.id}/></AdminLayout></QueryClientProvider>;
 try{
  const mounted=render(view());await screen.findByLabelText('Post text');await waitFor(()=>expect(screen.getByLabelText('Post text')).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText('Post text'),{target:{value:'PRIVATE_ACTOR_A_UNSAVED_CAVEAT'}});
  // A late former-actor request can legitimately populate its scoped cache after
  // layout eviction; the destination actor detail is already available here.
  client.setQueryData(socialKeys.detail(other,initial.id),loaded);
  client.setQueryData([...socialKeys.root(other),'accounts'],accounts);
  client.setQueryData([...socialKeys.root(other),'system'],{...system,publishing_enabled:false});
  actor=other;mounted.rerender(view());
  expect(screen.getByLabelText('Post text')).toHaveValue('B authorized saved caption');
  expect(screen.queryByDisplayValue('PRIVATE_ACTOR_A_UNSAVED_CAVEAT')).toBeNull();
 }finally{client.clear();actor=actorId}
});
test('new manual draft local text retires on verified actor change without any cached post detail',async()=>{
 const client=new QueryClient({defaultOptions:{queries:{retry:false}}});actor=actorId;
 (api.get as jest.Mock).mockImplementation(async(path:string)=>({data:path.endsWith('/accounts')?{accounts}:path.endsWith('/system/status')?{...system,publishing_enabled:false}:{upload_available:false,library_available:false,allowed_mime_types:[],max_image_bytes:10485760,max_video_bytes:52428800,unavailable_reason:'Owned disabled media'}}));
 const view=()=> <QueryClientProvider client={client}><AdminLayout><SocialEditorPage/></AdminLayout></QueryClientProvider>;
 try{const mounted=render(view());await screen.findByLabelText('Post text');fireEvent.change(screen.getByLabelText('Post text'),{target:{value:'PRIVATE_UNSAVED_MANUAL_ACTOR_A'}});actor='00000000-0000-4000-8000-000000000099';mounted.rerender(view());expect(screen.getByLabelText('Post text')).toHaveValue('');expect(screen.queryByDisplayValue('PRIVATE_UNSAVED_MANUAL_ACTOR_A')).toBeNull()}finally{client.clear();actor=actorId}
});
