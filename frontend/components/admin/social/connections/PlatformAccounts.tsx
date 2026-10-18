'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useSocialAccounts } from '@/lib/hooks/useSocial';
import { ConnectionError } from '@/lib/api/socialConnections';
import { ConnectionPlatform, PlatformChoice, PlatformHealth, platformConnectionApi } from '@/lib/api/socialPlatformConnections';
import styles from '../social.module.css';

const labels = { threads: 'Threads', x: 'X', tiktok: 'TikTok' };
function ProviderAccounts({ provider, actor }: { provider: ConnectionPlatform; actor: string }) {
  const status=useQuery({queryKey:['social-platform-status',provider,actor],queryFn:()=>platformConnectionApi.status(provider),retry:false,refetchOnWindowFocus:false});
  const accounts=useSocialAccounts();
  const [choice,setChoice]=useState<PlatformChoice>();
  const [health,setHealth]=useState<PlatformHealth>();
  const [error,setError]=useState<string>();
  const [busy,setBusy]=useState(false);
  const [recover,setRecover]=useState<string>();
  const pending=useRef<{popup:Window;state:string;redirect:string;key:string}|null>(null);
  const confirmKey=useRef<string | undefined>(undefined);
  const mounted=useRef(true);
  const storageKey=`auditgava-platform-flow:${actor}:${provider}`;
  const remember=useCallback((id?:string)=>{try{if(id)sessionStorage.setItem(storageKey,id);else sessionStorage.removeItem(storageKey);}catch{setError('Browser recovery storage is unavailable. Keep this page open until identity confirmation.');}},[storageKey]);
  useEffect(()=>{mounted.current=true;try{const id=sessionStorage.getItem(storageKey);if(id&&/^[0-9a-f-]{36}$/.test(id))setRecover(id);}catch{setError('Browser recovery storage is unavailable.');}return()=>{mounted.current=false;pending.current?.popup.close();pending.current=null;};},[storageKey]);
  useEffect(()=>{
    const receive=async(event:MessageEvent)=>{
      const flow=pending.current,v=event.data;
      if(!flow||event.source!==flow.popup||event.origin!==window.location.origin||!v||typeof v!=='object'||Array.isArray(v)||v.type!=='auditgava-platform-callback'||v.state!==flow.state||typeof v.denied!=='boolean'||Object.keys(v).some(k=>!['type','code','state','denied'].includes(k)))return;
      if(!v.denied&&(typeof v.code!=='string'||!v.code.length||v.code.length>4096))return;
      pending.current=null;flow.popup.close();setBusy(true);
      try{if(v.denied)throw new ConnectionError('OAUTH_DENIED','Authorization was declined. Start a new connection.');const result=await platformConnectionApi.complete(provider,v.code,flow.state,flow.redirect,flow.key);if(mounted.current){setChoice(result);confirmKey.current=crypto.randomUUID();setRecover(result.flow_id);}}
      catch(e){if(mounted.current)setError(e instanceof Error?e.message:'Connection failed. Recover its durable identity before restarting.');}
      finally{if(mounted.current)setBusy(false);}
    };
    window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive);
  },[provider]);
  async function start(){
    if(!status.data?.available||busy)return;
    const popup=window.open('about:blank',`AuditGava-${provider}`,'popup,width=700,height=760');
    if(!popup){setError('Allow the connection popup to continue.');return;}
    setBusy(true);setError(undefined);pending.current?.popup.close();
    const redirect=window.location.origin+'/admin/social/accounts/platform-callback'+(provider==='tiktok'?'/':'');
    try{const flow=await platformConnectionApi.start(provider,redirect,crypto.randomUUID());if(!mounted.current){popup.close();return;}const url=new URL(flow.authorize_url);if(url.searchParams.get('redirect_uri')!==redirect||Date.parse(flow.expires_at)<=Date.now())throw new Error('The provider callback or flow expiry could not be verified.');remember(flow.flow_id);setRecover(flow.flow_id);pending.current={popup,state:url.searchParams.get('state')!,redirect,key:crypto.randomUUID()};popup.location.replace(url.href);}
    catch(e){popup.close();if(mounted.current)setError(e instanceof Error?e.message:'Connection failed.');}
    finally{if(mounted.current)setBusy(false);}
  }
  async function recoverChoice(){if(!recover||busy)return;setBusy(true);try{const c=await platformConnectionApi.choice(provider,recover);if(mounted.current){setChoice(c);confirmKey.current??=crypto.randomUUID();}}catch(e){if(mounted.current)setError(e instanceof Error?e.message:'Recovery failed.');}finally{if(mounted.current)setBusy(false);}}
  async function confirm(){if(!choice||busy)return;setBusy(true);try{await platformConnectionApi.confirm(provider,choice,confirmKey.current??=crypto.randomUUID());if(mounted.current){remember();setChoice(undefined);setRecover(undefined);await accounts.refetch();}}catch(e){if(mounted.current)setError(e instanceof Error?e.message:'Identity confirmation failed.');}finally{if(mounted.current)setBusy(false);}}
  async function inspect(id:string){setBusy(true);setError(undefined);try{const h=await platformConnectionApi.health(provider,id);if(mounted.current)setHealth(h);}catch(e){if(mounted.current)setError(e instanceof Error?e.message:'Account health unavailable.');}finally{if(mounted.current)setBusy(false);}}
  async function command(action:'refresh'|'disconnect'){if(!health||busy)return;setBusy(true);try{const h=await platformConnectionApi.accountCommand(provider,health.account_id,action,health,crypto.randomUUID());if(mounted.current){setHealth(h);await accounts.refetch();}}catch(e){if(mounted.current)setError(e instanceof Error?e.message:'Account command failed.');}finally{if(mounted.current)setBusy(false);}}
  return <section className={styles.accountCard} aria-label={`${labels[provider]} accounts`}><h2>{labels[provider]}</h2>
    {provider==='threads'&&<p>Separate Threads OAuth, container processing and rolling quota checks. Public visibility needs separate confirmation for private profiles.</p>}
    {provider==='x'&&<p>Paid API access and a positive authorized budget are required for every request, including status and reconciliation. Zero budget blocks API activity.</p>}
    {provider==='tiktok'&&<p>Available only with genuine approved Accounts API access and verified media origins. Direct publication and delivery to the creator’s draft inbox have different outcomes.</p>}
    {status.isPending&&<p role='status'>Checking connection access…</p>}
    {(status.error||error)&&<p role='alert'>{error??'Platform status could not be loaded.'}</p>}
    {status.data&&<><p>Contract: {status.data.provider_api_version}. Publishing remains disabled on connection.</p>{!status.data.available&&<p className={styles.notice}>Unavailable: {status.data.blockers.join(' · ')}</p>}<p className={styles.muted}>Requested permissions: {status.data.scopes.join(', ')||'None available'}</p></>}
    <div className={styles.actions}><button type='button' className={styles.button} disabled={busy||!status.data?.available||!!status.error} onClick={start}>Connect {labels[provider]}</button><button type='button' className={styles.button} disabled={busy} onClick={()=>status.refetch()}>Refresh {labels[provider]} access</button>{recover&&<button type='button' className={styles.button} disabled={busy} onClick={recoverChoice}>Recover {labels[provider]} identity</button>}</div>
    {choice&&<div className={styles.notice}><h3>Confirm exact identity</h3><p>{choice.display_name} · {choice.handle??'Handle unavailable'} · {choice.external_account_id}</p><p>Granted: {choice.granted_scopes.join(', ')}</p><button type='button' className={styles.button} disabled={busy||Date.parse(choice.expires_at)<=Date.now()} onClick={confirm}>Confirm {labels[provider]} identity</button></div>}
    {accounts.data?.filter(a=>a.platform===provider).map(a=><div key={a.id}><h3>{a.display_name}</h3><p>{a.connection_state} · Publishing {a.publishing_enabled?'enabled':'disabled'}</p><button type='button' className={styles.button} disabled={busy} onClick={()=>inspect(a.id)}>Inspect {a.display_name} connection</button></div>)}
    {health&&<div className={styles.notice}><p>Credential version {health.credential_version} · Expiry {new Date(health.access_expires_at).toLocaleString()}</p><p>{health.refresh_pending?'Renewal outcome needs reconciliation.':health.reconnect_required?'Reconnect required.':'Current local credential is usable; provider access remains revocable.'}</p><div className={styles.actions}><button type='button' className={styles.button} disabled={busy||health.refresh_pending||!status.data?.available} onClick={()=>command('refresh')}>Renew existing grant</button><button type='button' className={styles.button} disabled={busy||health.connection_state==='disconnected'} onClick={()=>command('disconnect')}>Disable local connection</button></div></div>}
  </section>;
}
export default function PlatformAccounts(){const {user}=useAuth();return <div className={styles.workspace} aria-label='Additional platform accounts'>{(['threads','x','tiktok'] as const).map(provider=><ProviderAccounts key={`${user?.id}:${provider}`} provider={provider} actor={user?.id??'signed-out'} />)}</div>;}
