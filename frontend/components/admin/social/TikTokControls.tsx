'use client';
import { useEffect, useRef, useState } from 'react';
import { DocumentTarget, TikTokPostOptions } from '@/lib/api/social';
import { CreatorSettings, platformConnectionApi } from '@/lib/api/socialPlatformConnections';
import styles from './social.module.css';

export default function TikTokControls({ target, onChange }: { target:DocumentTarget; onChange:(target:DocumentTarget)=>void }) {
  const [settings,setSettings]=useState<CreatorSettings>();
  const [error,setError]=useState<string>();
  const [busy,setBusy]=useState(false);
  const [mode,setMode]=useState<TikTokPostOptions['mode']|''>(target.tiktok_options?.mode??'');
  const options=target.tiktok_options;
  const latest=useRef({target,onChange});
  latest.current={target,onChange};
  const alive=useRef(true);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  const [expired,setExpired]=useState(false);
  useEffect(()=>{if(!settings){setExpired(false);return;}const delay=Date.parse(settings.checked_at)+300000-Date.now();setExpired(delay<=0);const timer=window.setTimeout(()=>setExpired(true),Math.max(0,delay));return()=>window.clearTimeout(timer);},[settings]);
  async function refresh(){setBusy(true);setError(undefined);try{const result=await platformConnectionApi.creatorSettings(target.account_id);if(!alive.current)return;setSettings(result);const clean={...latest.current.target};delete clean.tiktok_options;latest.current.onChange(clean);}catch(e){if(alive.current)setError(e instanceof Error?e.message:'Current creator settings are unavailable.');}finally{if(alive.current)setBusy(false);}}
  function choose(privacy:TikTokPostOptions['privacy_level']|'',nextMode=mode){if(!privacy||!nextMode||!settings)return;onChange({...target,tiktok_options:{mode:nextMode,privacy_level:privacy,disable_comment:true,disable_duet:true,disable_stitch:true,commercial_content:false,is_brand_organic:false,is_branded_content:false,is_ai_generated:false,upload_consent:false,music_usage_confirmed:false,branded_content_policy_confirmed:false,creator_settings_checked_at:settings.checked_at,creator_settings_hash:settings.settings_hash,photo_title:''}});}
  function update(changes:Partial<TikTokPostOptions>){if(options)onChange({...target,tiktok_options:{...options,...changes}});}
  return <section className={styles.fields} aria-label='TikTok creator choices'><h3>TikTok creator choices</h3><p>Review current account settings, choose a destination and privacy, then confirm the exact content. Upload and publishing controls remain separate.</p>
    <button type='button' className={styles.button} disabled={busy} onClick={refresh}>{busy?'Reading creator settings…':'Read current TikTok settings'}</button>
    {error&&<p role='alert'>{error}</p>}{expired&&<p role='alert'>Creator settings are stale. Read them again before authorizing this revision.</p>}
    {settings&&<><p>{settings.display_name} · {settings.handle??'Handle unavailable'} · {settings.external_account_id}</p><p>Maximum video duration: {settings.settings.max_video_post_duration_sec} seconds.</p>
      <label>Delivery workflow<select value={mode} onChange={e=>{const next=e.target.value as TikTokPostOptions['mode'];setMode(next);if(options)choose(options.privacy_level,next);}}><option value=''>Choose a workflow</option><option value='direct'>Direct publication</option><option value='draft'>Send to creator’s draft inbox</option></select></label>
      <label>Privacy<select disabled={!mode||expired} value={options?.privacy_level??''} onChange={e=>choose(e.target.value as TikTokPostOptions['privacy_level'])}><option value=''>Choose privacy explicitly</option>{settings.settings.privacy_level_options.map(value=><option key={value} value={value} disabled={value==='SELF_ONLY'&&!!options?.is_branded_content}>{value.replaceAll('_',' ')}</option>)}</select></label>
      {mode==='draft'&&<p className={styles.notice}>Delivery to the draft inbox requires the creator to finish in TikTok. It is never reported as a public post. TikTok ignores direct-publication privacy and interaction metadata for drafts.</p>}
      {options&&<fieldset disabled={expired} className={styles.fields}>
        {mode==='direct'&&<>{(['comment','duet','stitch'] as const).filter(kind=>kind==='comment'||target.format==='video').map(kind=><label key={kind} className={styles.reviewCheck}><input type='checkbox' disabled={settings.settings[`${kind}_disabled`]} checked={!options[`disable_${kind}`]} onChange={e=>update({[`disable_${kind}`]:!e.target.checked})}/><span>Allow {kind}{settings.settings[`${kind}_disabled`]?' · disabled by the creator':''}</span></label>)}
          {target.format!=='video'&&<label>Photo title<input maxLength={90} value={options.photo_title} onChange={e=>update({photo_title:e.target.value})}/></label>}
          <label className={styles.reviewCheck}><input type='checkbox' checked={options.commercial_content} onChange={e=>update({commercial_content:e.target.checked,is_brand_organic:false,is_branded_content:false,branded_content_policy_confirmed:false})}/><span>This content promotes a brand, product or service</span></label>
          {options.commercial_content&&<><label className={styles.reviewCheck}><input type='checkbox' checked={options.is_brand_organic} onChange={e=>update({is_brand_organic:e.target.checked})}/><span>Your brand · Promotional content</span></label><label className={styles.reviewCheck}><input type='checkbox' checked={options.is_branded_content} disabled={options.privacy_level==='SELF_ONLY'} onChange={e=>update({is_branded_content:e.target.checked,branded_content_policy_confirmed:false})}/><span>Branded content · Paid partnership (cannot be private)</span></label></>}
          <label className={styles.reviewCheck}><input type='checkbox' checked={options.is_ai_generated} onChange={e=>update({is_ai_generated:e.target.checked})}/><span>Disclose AI-generated content</span></label></>}
        <label className={styles.reviewCheck}><input type='checkbox' checked={options.upload_consent} onChange={e=>update({upload_consent:e.target.checked})}/><span>I consent to send this exact reviewed content to this TikTok account.</span></label>
        <label className={styles.reviewCheck}><input type='checkbox' checked={options.music_usage_confirmed} onChange={e=>update({music_usage_confirmed:e.target.checked})}/><span>By posting, I agree to TikTok’s Music Usage Confirmation.</span></label>
        {options.is_branded_content&&<label className={styles.reviewCheck}><input type='checkbox' checked={options.branded_content_policy_confirmed} onChange={e=>update({branded_content_policy_confirmed:e.target.checked})}/><span>I agree to TikTok’s Branded Content Policy.</span></label>}
      </fieldset>}
    </>}
    {options&&!settings&&<p className={styles.notice}>This revision has saved TikTok choices. Read current settings to review and renew consent before making a new authorization.</p>}
  </section>;
}
