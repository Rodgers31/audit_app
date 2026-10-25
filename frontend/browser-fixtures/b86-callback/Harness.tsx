'use client';
import {useEffect,useState} from 'react';
import MetaAccounts from '@/components/admin/social/connections/MetaAccounts';
export default function Harness(){
  const [hint,setHint]=useState('No callback message received');
  useEffect(()=>{const listener=(e:MessageEvent)=>{if(e.origin===location.origin)setHint(JSON.stringify(e.data));};window.addEventListener('message',listener);return()=>window.removeEventListener('message',listener);},[]);
  return <main style={{fontFamily:'Arial,sans-serif',maxWidth:1000,margin:'auto',padding:20}}><h1>Owned inert callback fixture</h1><p>No real OAuth, provider, credentials, account writes or production collector acceptance.</p><MetaAccounts/><section><h2>Actual API callback script</h2><button onClick={()=>window.open('/api/v1/social/oauth/meta/callback?code=INERT-browser-code&state=INERT-browser-state','B86InertCallback','popup,width=650,height=500')}>Open inert callback response</button><p role='status'>{hint}</p></section></main>
}
