'use client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';
export default function Harness({children}:{children:ReactNode}) {
 const [dark,setDark]=useState(false);
 useEffect(()=>{document.documentElement.classList.toggle('dark',dark);},[dark]);
 const [client]=useState(()=>new QueryClient({defaultOptions:{queries:{retry:false}}}));
 return <QueryClientProvider client={client}><style>{`*{box-sizing:border-box}body{margin:0;font-family:'Public Sans',Arial,sans-serif;background:#f5f5ef}h1,h2,h3,p{margin:0}a{color:inherit}button,input,textarea,select{font:inherit}.fixture-banner{padding:12px 24px;background:#fff3d4;color:#503b1e;font-size:13px}`}</style><div className='fixture-banner'>LOCAL REVIEW FIXTURE · Existing engine output from the Nairobi reference draft · No provider connection · Publishing, uploads and workers OFF <button type='button' onClick={()=>setDark(!dark)}>Fixture theme: {dark?'dark':'light'}</button></div><main id='main-content'>{children}</main></QueryClientProvider>;
}
