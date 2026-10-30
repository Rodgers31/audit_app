import { act, cleanup, render } from '@testing-library/react';
import NavTrailTracker from '@/lib/navigation/NavTrailTracker';
import { retainHistoryTracking, useUnsavedHistoryGuard } from '@/lib/navigation/historyGuard';

jest.mock('next/navigation', () => ({ usePathname: () => window.location.pathname, useSearchParams: () => new URLSearchParams(window.location.search) }));
const nativePush = window.history.pushState;
const nativeReplace = window.history.replaceState;
const KEY = '__auditgavaHistory';
let sequence = 0;
const settle = async (milliseconds=55) => act(async () => { await new Promise(resolve => setTimeout(resolve, milliseconds)); });
function Guard({dirty}:{dirty:boolean}) { useUnsavedHistoryGuard(dirty); return <div>Editor</div>; }
function Tree({dirty,actor='A'}:{dirty:boolean;actor?:string}) { return <><NavTrailTracker/><Guard key={actor} dirty={dirty}/></>; }
function seed() {
  sequence++;
  nativeReplace.call(window.history, {__NA:true,seed:sequence}, '', '/seed-'+sequence);
  sessionStorage.clear();
}
function paths() {
  return [0,1,2,3,4].map(i => '/case-'+sequence+'/'+i+'?page='+i+'#section-'+i);
}
function push(url:string, i:number) { window.history.pushState({__NA:true,__PRIVATE_NEXTJS_INTERNALS_TREE:{i,segments:['admin','social']},opaque:{revision:7},idx:i},'',url); }
async function traverse(delta:number) { act(() => window.history.go(delta)); await settle(); }
afterEach(async () => { cleanup(); await settle(20); jest.restoreAllMocks(); window.history.pushState=nativePush;window.history.replaceState=nativeReplace; sessionStorage.clear(); });

it.each([-1,-2,-4])('cancel then accept preserves a tracked backward jump %s', async delta => {
  seed();const urls=paths();const tree=render(<Tree dirty={false}/>);urls.forEach(push);tree.rerender(<Tree dirty/>);
  const confirm=jest.spyOn(window,'confirm').mockReturnValue(false);const next=jest.fn();window.addEventListener('popstate',next);
  try {
    const length=window.history.length;await traverse(delta);
    expect(window.location.href).toContain(urls[4]);expect(next).not.toHaveBeenCalled();expect(window.history.length).toBe(length);
    confirm.mockReturnValue(true);await traverse(delta);
    expect(window.location.href).toContain(urls[4+delta]);expect(next).toHaveBeenCalledTimes(1);expect(confirm).toHaveBeenCalledTimes(2);
  } finally {window.removeEventListener('popstate',next);}
});

it.each([1,2,3])('cancel then accept a multi-entry forward jump %s', async delta => {
  seed();const urls=paths();const tree=render(<Tree dirty={false}/>);urls.forEach(push);await traverse(-3);tree.rerender(<Tree dirty/>);
  const confirm=jest.spyOn(window,'confirm').mockReturnValue(false);await traverse(delta);expect(window.location.href).toContain(urls[1]);
  confirm.mockReturnValue(true);await traverse(delta);expect(window.location.href).toContain(urls[1+delta]);expect(confirm).toHaveBeenCalledTimes(2);
});

it('repeated cancellation retains both query and forward history', async()=>{
  seed();const urls=paths();const tree=render(<Tree dirty={false}/>);urls.forEach(push);await traverse(-2);tree.rerender(<Tree dirty/>);
  const confirm=jest.spyOn(window,'confirm').mockReturnValue(false);
  await traverse(-2);await traverse(2);await traverse(-1);expect(window.location.href).toContain(urls[2]);
  confirm.mockReturnValue(true);await traverse(2);expect(window.location.href).toContain(urls[4]);expect(confirm).toHaveBeenCalledTimes(4);
});

it('tracked replace keeps the same traversal position and all Next state fields', async()=>{
  seed();const tree=render(<Tree dirty={false}/>);push('/before',1);push('/editor',2);
  const point=window.history.state[KEY];const data={__NA:true,__PRIVATE_NEXTJS_INTERNALS_TREE:{segments:['x'],parallelRoutes:{children:{}}},__N:true,options:{scroll:false},key:'opaque'};
  window.history.replaceState(data,'','/editor?draft=2');expect(window.history.state).toMatchObject(data);expect(window.history.state[KEY]).toEqual(point);
  tree.rerender(<Tree dirty/>);jest.spyOn(window,'confirm').mockReturnValue(false);await traverse(-1);
  expect(window.location.pathname+window.location.search).toBe('/editor?draft=2');expect(window.history.state).toMatchObject(data);
});

it.each(['clean','save','unmount','actor'] as const)('%s retires the dirty guard without trapping navigation',async mode=>{
  seed();const tree=render(<Tree dirty={mode!=='clean'}/>);push('/previous',1);push('/editor',2);const confirm=jest.spyOn(window,'confirm').mockReturnValue(false);
  if(mode==='save')tree.rerender(<Tree dirty={false}/>);
  if(mode==='actor')tree.rerender(<Tree dirty={false} actor='B'/>);
  if(mode==='unmount')tree.rerender(<NavTrailTracker/>);
  await traverse(-1);expect(window.location.pathname).toBe('/previous');expect(confirm).not.toHaveBeenCalled();
});

it('releasing one tracker owner keeps the other owner active and finally restores method identities',()=>{
  seed();const p=window.history.pushState,r=window.history.replaceState;const first=retainHistoryTracking(),second=retainHistoryTracking();
  first();push('/retained',1);expect(window.history.state[KEY]).toBeDefined();second();expect(window.history.pushState).toBe(p);expect(window.history.replaceState).toBe(r);
});

it.each([null,'opaque',42,true,{other:true}])('unknown pretracking state %j restores the dirty editor and can later leave',async unknown=>{
  seed();nativePush.call(window.history,unknown,'','/unknown');nativePush.call(window.history,{__NA:true,tree:{current:'editor'}},'','/editor');
  render(<Tree dirty/>);const confirm=jest.spyOn(window,'confirm').mockReturnValue(false);
  await traverse(-1);expect(window.location.pathname).toBe('/editor');expect(window.history.state.tree).toEqual({current:'editor'});
  confirm.mockReturnValue(true);await traverse(-1);expect(window.location.pathname).toBe('/unknown');expect(confirm).toHaveBeenCalledTimes(2);
});

it.each([true,0.5,NaN,Infinity,'2',null])('malformed position %s is treated as unknown without stranding the editor',async position=>{
  seed();const tree=render(<Tree dirty={false}/>);push('/previous',1);const point=window.history.state[KEY];
  nativeReplace.call(window.history,{__NA:true,[KEY]:{...point,position}},'','/previous');push('/editor',2);tree.rerender(<Tree dirty/>);
  jest.spyOn(window,'confirm').mockReturnValue(false);await traverse(-1);expect(window.location.pathname).toBe('/editor');
});

it.each([-1,999999])('out-of-range own-document position %s must not strand the dirty editor',async position=>{
  seed();const tree=render(<Tree dirty={false}/>);push('/previous',1);const point=window.history.state[KEY];
  nativeReplace.call(window.history,{__NA:true,[KEY]:{...point,position}},'','/previous');push('/editor',2);tree.rerender(<Tree dirty/>);
  jest.spyOn(window,'confirm').mockReturnValue(false);await traverse(-1);expect(window.location.pathname).toBe('/editor');
});

it('rapid repeated backward traversal cancels without losing subsequent accepted traversal',async()=>{
  seed();const tree=render(<Tree dirty={false}/>);const urls=paths();urls.forEach(push);tree.rerender(<Tree dirty/>);
  const confirm=jest.spyOn(window,'confirm').mockReturnValue(false);act(()=>{window.history.go(-3);window.history.go(-1);window.history.go(-2);});await settle(120);
  expect(window.location.href).toContain(urls[4]);confirm.mockReturnValue(true);await traverse(-2);expect(window.location.href).toContain(urls[2]);
});

it('capturing router observer mounted first still cannot unmount the editor on cancellation',async()=>{
  seed();const bubble=jest.fn();window.addEventListener('popstate',bubble);
  try {const tree=render(<Tree dirty={false}/>);push('/before',1);push('/editor',2);tree.rerender(<Tree dirty/>);jest.spyOn(window,'confirm').mockReturnValue(false);await traverse(-1);expect(bubble).not.toHaveBeenCalled();expect(window.location.pathname).toBe('/editor');}
  finally {window.removeEventListener('popstate',bubble);}
});
