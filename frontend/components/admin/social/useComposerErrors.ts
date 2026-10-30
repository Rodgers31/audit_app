'use client';
import {useEffect,useId,useMemo,useRef,useState} from 'react';
import type {DocumentTarget,SocialApiError,SocialIssue} from '@/lib/api/social';
import {socialIssueKey} from './socialIssue';

export interface ComposerFieldProps {
  id: string;
  'data-social-field': string;
  'aria-invalid'?: boolean;
  'aria-describedby'?: string;
}
/** Canonical request paths, not a separate list of form-specific exceptions. */
function issuePath(issue: SocialIssue, targets: DocumentTarget[]): string | undefined {
  let path=issue.field.replace(/^body\./,'').replace(/\[(\d+)\]/g,'.$1');
  if(issue.account_id){
    const index=targets.findIndex(target=>target.account_id===issue.account_id);
    if(index<0)return;
    if(!path.startsWith('document.targets.'))path=`document.targets.${index}.${path}`;
    if(!path.startsWith(`document.targets.${index}.`))return;
  }
  if(['text','link','hashtags','media'].includes(path))path='document.master.'+path;
  if(path.startsWith('master.'))path='document.'+path;
  return /^(?:title|content_type|document(?:\.|$)|references(?:\.|$))/.test(path)?path:undefined;
}
function within(issue: string, field: string) {return issue===field||issue.startsWith(field+'.');}

export default function useComposerErrors(error: SocialApiError|undefined,targets:DocumentTarget[],activeAccount:string,setActiveAccount:(id:string)=>void,mobilePanel:'editor'|'preview',setMobilePanel:(panel:'editor'|'preview')=>void){
  const context=useId().replaceAll(':','');
  const errorId=`social-command-error-${context}`;
  const editorRef=useRef<HTMLElement>(null);
  const [fieldLinks,setFieldLinks]=useState<Record<string,string>>({});
  const [recoveryVersion,setRecoveryVersion]=useState(0);
  const lastError=useRef<SocialApiError|undefined>(undefined);
  const recovery=useRef<{path?:string;focusField:boolean}|undefined>(undefined);
  const issues=useMemo(()=>[...(error?.fieldErrors??[]),...(error?.targetErrors??[])].flatMap(issue=>{const path=issuePath(issue,targets);return path?[{key:socialIssueKey(issue),path}]:[];}),[error,targets]);
  const fieldId=(path:string)=>`${errorId}-field-${path.replaceAll('.','-')}`;
  function fieldIssueProps(path:string):ComposerFieldProps{return {id:fieldId(path),'data-social-field':path,'aria-invalid':issues.some(issue=>within(issue.path,path))||undefined,'aria-describedby':issues.some(issue=>within(issue.path,path))?errorId:undefined};}
  useEffect(()=>{
    if(!error){setFieldLinks({});lastError.current=undefined;recovery.current=undefined;return;}
    if(lastError.current!==error){lastError.current=error;recovery.current={path:issues[0]?.path,focusField:false};}
    const request=recovery.current;
    if(!request)return;
    const preferred=request.path;
    const targetIndex=preferred?.match(/^document\.targets\.(\d+)(?:\.|$)/)?.[1];
    const selected=targetIndex===undefined?undefined:targets[Number(targetIndex)]?.account_id;
    if(selected&&selected!==activeAccount){setActiveAccount(selected);return;}
    const fields=Array.from(editorRef.current?.querySelectorAll<HTMLElement>('[data-social-field]')??[]);
    const find=(path:string)=>fields.filter(field=>within(path,field.dataset.socialField!)).sort((a,b)=>b.dataset.socialField!.length-a.dataset.socialField!.length)[0];
    const links:Record<string,string>={};
    for(const issue of issues){
      const field=find(issue.path);
      const targetGroup=issue.path.match(/^document\.targets\.\d+(?:\.|$)/)?.[0].replace(/\.$/,'');
      if(!field){if(targetGroup)links[issue.key]=fieldId(targetGroup);continue;}
      links[issue.key]=field.id;
      for(let parent=field.parentElement;parent&&parent!==editorRef.current;parent=parent.parentElement){if(parent instanceof HTMLDetailsElement)parent.open=true;}
    }
    setFieldLinks(links);
    const field=preferred?find(preferred):undefined;
    const panel=field?.closest<HTMLElement>('[data-composer-panel]')?.dataset.composerPanel;
    if((panel==='editor'||panel==='preview')&&panel!==mobilePanel){setMobilePanel(panel);return;}
    if(request.focusField&&field){field.focus();field.scrollIntoView?.({block:'center'});}
    else document.getElementById(errorId)?.focus();
    recovery.current=undefined;
  // A new error or destination/panel transition must resolve against the mounted controls.
  },[error,issues,targets,activeAccount,mobilePanel,recoveryVersion,errorId,setActiveAccount,setMobilePanel]);
  return {editorRef,errorId,fieldIssueProps,fieldLinks,selectField:(issue:SocialIssue)=>{
    const path=issues.find(candidate=>candidate.key===socialIssueKey(issue))?.path;
    if(path){recovery.current={path,focusField:true};setRecoveryVersion(version=>version+1);}
  }};
}
