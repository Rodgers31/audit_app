import {act,cleanup,render} from '@testing-library/react';
import NavTrailTracker from '@/lib/navigation/NavTrailTracker';
import {useUnsavedHistoryGuard} from '@/lib/navigation/historyGuard';
jest.mock('next/navigation',()=>({usePathname:()=>window.location.pathname,useSearchParams:()=>new URLSearchParams(window.location.search)}));
const settle=async()=>act(async()=>{await new Promise(resolve=>setTimeout(resolve,80));});
function Guard({dirty}:{dirty:boolean}){useUnsavedHistoryGuard(dirty);return <p>Retained new draft</p>;}
function Tree({dirty}:{dirty:boolean}){return <><NavTrailTracker/><Guard dirty={dirty}/></>;}
afterEach(()=>{cleanup();jest.restoreAllMocks();});
it('cancelled unknown Forward cannot corrupt a later multi-entry cancellation delta',async()=>{
 expect(window.history.length).toBe(1);
 window.history.replaceState({},'','/original-editor');window.history.pushState({},'','/pretracking-forward');act(()=>window.history.back());await settle();
 const tree=render(<Tree dirty/>);const confirm=jest.spyOn(window,'confirm').mockReturnValue(false);
 act(()=>window.history.forward());await settle();expect(window.location.pathname).toBe('/original-editor');
 tree.rerender(<Tree dirty={false}/>);window.history.pushState({},'','/new-editor');tree.rerender(<Tree dirty/>);
 act(()=>window.history.go(-3));await settle();
 expect(confirm).toHaveBeenCalledTimes(2);expect(window.location.pathname).toBe('/new-editor');
});
