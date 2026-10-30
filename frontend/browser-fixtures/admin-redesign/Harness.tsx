'use client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';
import comparisonExamples from './comparison-examples.json';
import { LangProvider } from '@/lib/i18n/LangProvider';
import { socialMediaApi } from '@/lib/api/socialMedia';
import { fixtureAsset } from './media';
// Explicit loopback harness substitute; the product storage decoder stays strict.
socialMediaApi.preview=async id=>{if(id!==fixtureAsset.id)throw new Error('Unknown local fixture');return {asset:fixtureAsset,url:'/fixture-media.png',expires_at:new Date(Date.now()+299000).toISOString()};};
export default function Harness({children}:{children:ReactNode}) {
 const [dark,setDark]=useState(false);
 useEffect(()=>{document.documentElement.classList.toggle('dark',dark);},[dark]);
 const [client]=useState(()=>new QueryClient({defaultOptions:{queries:{retry:false}}}));
 useEffect(()=>{const openLocal=(event:MouseEvent)=>{const anchor=(event.target as HTMLElement).closest('a');if(!anchor)return;const url=new URL(anchor.href);if(url.hostname==='www.auditgava.com'&&comparisonExamples.some(s=>s.link===url.href)){event.preventDefault();window.location.assign(url.pathname+url.search);}};document.addEventListener('click',openLocal);return()=>document.removeEventListener('click',openLocal);},[]);
 return <LangProvider><QueryClientProvider client={client}><style>{`*{box-sizing:border-box}body{margin:0;font-family:'Public Sans',Arial,sans-serif;background:#f5f5ef}h1,h2,h3,p{margin:0}a{color:inherit}button,input,textarea,select{font:inherit}.fixture-banner{padding:12px 24px;background:#fff3d4;color:#503b1e;font-size:13px}.fixture-links{display:flex;flex-wrap:wrap;gap:8px 20px;margin-top:8px}.fixture-links a{text-decoration:underline}`}</style><div className='fixture-banner'>LOCAL REVIEW FIXTURE · Illustrative amounts and evidence · AuditGava post links open matching local samples · Publishing, uploads and workers OFF <button type='button' onClick={()=>setDark(!dark)}>Fixture theme: {dark?'dark':'light'}</button><nav aria-label='Sample previews' className='fixture-links'>{comparisonExamples.map(sample=><a key={sample.id} href={'/admin/social/'+sample.id}>{sample.label} preview</a>)}<a href='/admin/social'>All sample drafts</a><a href='/counties/nairobi-county?tab=budget&as_at=2026-06-30#pending-bills'>Nairobi local destination</a></nav></div><main id='main-content'>{children}</main></QueryClientProvider></LangProvider>;
}
