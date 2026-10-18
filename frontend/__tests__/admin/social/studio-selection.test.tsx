import SocialStudio from '@/components/admin/social/SocialStudio';
import { socialApi } from '@/lib/api/social';
import { socialMediaApi } from '@/lib/api/socialMedia';
import { studioApi } from '@/lib/api/socialStudio';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { post } from '../../../tests/socialFixtures';
jest.mock('@/lib/api/social', () => ({ ...jest.requireActual('@/lib/api/social'), socialApi: { posts:jest.fn(), post:jest.fn() } }));
jest.mock('@/lib/api/socialMedia', () => ({ socialMediaApi: { library:jest.fn() } }));
jest.mock('@/lib/api/socialStudio', () => ({ ...jest.requireActual('@/lib/api/socialStudio'), studioApi: { capabilities:jest.fn(), jobs:jest.fn(), calendar:jest.fn(), attach:jest.fn() } }));
const source=post({ title:'Older source', version:7 });
const job={ id:'job', revision_id:source.revision_id, state:'ready', version:3, composition:{title:'Existing render',kind:'graphic',facts:[],scenes:[]},sha256:'a'.repeat(64),approved_sha256:'a'.repeat(64) };
const asset={ id:'exact',filename:'Older exact.png',state:'ready',sha256:job.sha256,mime_type:'image/png' };
let qc:QueryClient;
beforeEach(() => {
 jest.clearAllMocks(); Object.defineProperty(crypto,'randomUUID',{configurable:true,value:()=> 'fixture-key'});
 qc=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}});
 (socialApi.posts as jest.Mock).mockImplementation(async page=>({posts:page===1?Array.from({length:20},(_,i)=>({...source,id:`p${i}`,title:`New ${i}`})):[source],page,has_more:page===1}));
 (socialApi.post as jest.Mock).mockResolvedValue(source);
 (socialMediaApi.library as jest.Mock).mockImplementation(async page=>({assets:page===1?Array.from({length:20},(_,i)=>({...asset,id:`a${i}`,sha256:'b'.repeat(64)})):[asset],page,has_more:page===1}));
 (studioApi.capabilities as jest.Mock).mockResolvedValue({rendering_available:false});
 (studioApi.jobs as jest.Mock).mockResolvedValue({jobs:[job],has_more:false});
 (studioApi.calendar as jest.Mock).mockResolvedValue({items:[],has_more:false});
 (studioApi.attach as jest.Mock).mockResolvedValue({...source,version:8});
});
afterEach(()=>qc.clear());
async function older(){
 render(<QueryClientProvider client={qc}><SocialStudio/></QueryClientProvider>);
 fireEvent.click(await screen.findByRole('button',{name:/Existing render/}));
 fireEvent.click(await screen.findByRole('button',{name:'Next source posts'}));
 await screen.findByRole('option',{name:'Older source'});
 fireEvent.change(screen.getByLabelText('Source post'),{target:{value:source.id}});
 fireEvent.click(await screen.findByRole('button',{name:'Next asset page'}));
 await screen.findByRole('option',{name:'Older exact.png'});
 fireEvent.change(screen.getByLabelText('Matching inspected asset'),{target:{value:asset.id}});
}
test('bounded pages reach older source and exact derivative',async()=>{
 await older(); const button=screen.getByRole('button',{name:'Add approved derivative to source draft'});
 await waitFor(()=>expect(button).toBeEnabled()); fireEvent.click(button);
 await waitFor(()=>expect(studioApi.attach).toHaveBeenCalledWith(job,asset.id,7,'fixture-key'));
 expect(socialApi.posts).toHaveBeenCalledTimes(2); expect(socialMediaApi.library).toHaveBeenCalledTimes(2);
});
test('moving away from selected asset page refuses attachment',async()=>{
 await older(); fireEvent.click(screen.getByRole('button',{name:'Previous asset page'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Add approved derivative to source draft'})).toBeDisabled());
});
test('changed source revision refuses attachment',async()=>{
 (socialApi.post as jest.Mock).mockResolvedValue({...source,revision_id:'changed'}); await older();
 expect(screen.getByRole('button',{name:'Add approved derivative to source draft'})).toBeDisabled();
});

function attachButton(){return screen.getByRole('button',{name:'Add approved derivative to source draft'});}
test('independent: wrong hash, mime and non-ready asset excluded',async()=>{
 (socialMediaApi.library as jest.Mock).mockImplementation(async page=>({assets:page===1?[]:[{...asset,id:'wronghash',sha256:'c'.repeat(64)},{...asset,id:'wrongmime',mime_type:'video/mp4'},{...asset,id:'uninspected',state:'pending'},asset],has_more:page===1}));
 await older(); expect(screen.getAllByRole('option',{name:'Older exact.png'})).toHaveLength(1);
 await waitFor(()=>expect(attachButton()).toBeEnabled());
});
test('independent: cached source refetch failure disables attachment',async()=>{
 await older(); await waitFor(()=>expect(attachButton()).toBeEnabled());
 (socialApi.post as jest.Mock).mockRejectedValue(new Error('offline'));
 await qc.invalidateQueries({queryKey:['studio-source']});
 await waitFor(()=>expect(attachButton()).toBeDisabled()); fireEvent.click(attachButton()); expect(studioApi.attach).not.toHaveBeenCalled();
});
test('independent: cached asset refetch failure disables attachment',async()=>{
 await older(); await waitFor(()=>expect(attachButton()).toBeEnabled());
 (socialMediaApi.library as jest.Mock).mockRejectedValue(new Error('offline'));
 await qc.invalidateQueries({queryKey:['studio-assets']});
 await waitFor(()=>expect(attachButton()).toBeDisabled()); fireEvent.click(attachButton()); expect(studioApi.attach).not.toHaveBeenCalled();
});
test('independent: changing source clears selected exact asset',async()=>{
 await older(); await waitFor(()=>expect(attachButton()).toBeEnabled());
 fireEvent.change(screen.getByLabelText('Source post'),{target:{value:''}});
 expect(attachButton()).toBeDisabled(); expect(screen.getByLabelText('Matching inspected asset')).toHaveValue('');
});
test('independent: source update while media is selected refuses stale revision',async()=>{
 await older(); await waitFor(()=>expect(attachButton()).toBeEnabled());
 qc.setQueryData(['studio-source',source.id],{...source,revision_id:'other-revision',version:8});
 await waitFor(()=>expect(attachButton()).toBeDisabled());
});
test('independent: pending source refetch blocks attachment',async()=>{
 await older(); await waitFor(()=>expect(attachButton()).toBeEnabled());
 let resolve:any; (socialApi.post as jest.Mock).mockImplementation(()=>new Promise(r=>{resolve=r;}));
 const pending=qc.invalidateQueries({queryKey:['studio-source']});
 await waitFor(()=>expect(attachButton()).toBeDisabled()); resolve(source); await pending;
 await waitFor(()=>expect(attachButton()).toBeEnabled());
});

test('independent: out-of-order source completion cannot restore prior source',async()=>{
 await older(); let resolve:any;
 (socialApi.post as jest.Mock).mockImplementation(()=>new Promise(r=>{resolve=r;}));
 const pending=qc.invalidateQueries({queryKey:['studio-source']});
 await waitFor(()=>expect(attachButton()).toBeDisabled());
 fireEvent.change(screen.getByLabelText('Source post'),{target:{value:''}}); resolve(source); await pending;
 expect(screen.getByLabelText('Source post')).toHaveValue(''); expect(screen.getByLabelText('Title · 70 characters')).toHaveValue(''); expect(attachButton()).toBeDisabled();
});
test('independent: cached job network failure disables attachment',async()=>{
 await older(); await waitFor(()=>expect(attachButton()).toBeEnabled());
 (studioApi.jobs as jest.Mock).mockRejectedValue(new Error('offline'));
 await qc.invalidateQueries({queryKey:['studio-jobs']});
 await waitFor(()=>expect(attachButton()).toBeDisabled());
});

test('concurrent attach conflict cannot show a success link or notice',async()=>{
 await older(); await waitFor(()=>expect(attachButton()).toBeEnabled());
 (studioApi.attach as jest.Mock).mockRejectedValue(new Error('VERSION_CONFLICT'));
 fireEvent.click(attachButton());
 await waitFor(()=>expect(studioApi.attach).toHaveBeenCalledTimes(1));
 await waitFor(()=>expect(screen.queryByRole('link',{name:'Review updated draft'})).not.toBeInTheDocument());
 expect(screen.queryByText(/Derivative added to a new draft revision/)).not.toBeInTheDocument();
});
test('late asset response for previous page cannot restore attachment',async()=>{
 await older(); await waitFor(()=>expect(attachButton()).toBeEnabled());
 let release:(value:unknown)=>void=()=>{};
 (socialMediaApi.library as jest.Mock).mockImplementation(page=>page===2?new Promise(r=>{release=r}):Promise.resolve({assets:[],has_more:true}));
 const pending=qc.invalidateQueries({queryKey:['studio-assets']});
 await waitFor(()=>expect(attachButton()).toBeDisabled());
 // Page buttons wait for the in-flight page; changing source clears the selection immediately.
 fireEvent.change(screen.getByLabelText('Source post'),{target:{value:''}});
 release({assets:[asset],has_more:false}); await pending;
 expect(attachButton()).toBeDisabled(); expect(screen.getByLabelText('Matching inspected asset')).toHaveValue('');
});
