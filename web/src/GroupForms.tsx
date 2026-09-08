// SPDX-License-Identifier: AGPL-3.0-or-later
import {useEffect,useId,useRef,useState} from 'react';
import {api} from './api';
import {groupText} from './group-text.mjs';
import {groupFailure,ownObservations} from './group-tools.mjs';
import {formatDataset, formatReferenceDate} from './i18n.mjs';
import type {Locale,Observation,Place} from './types';
export type Submission={action:'submit';observation_id:string;share_with_group:true};
export function ConfirmAction({label,help,disabled,run,locale}:{label:string;help:string;disabled:boolean;run:()=>Promise<boolean>;locale:Locale}) {
 const [open,setOpen]=useState(false),[agreed,setAgreed]=useState(false);
 const t=(key:string)=>groupText(locale,key);
 if(!open)return <button type="button" disabled={disabled} onClick={()=>setOpen(true)}>{label}</button>;
 return <form className="group-confirm" onSubmit={async e=>{e.preventDefault();if(agreed&&await run()){setOpen(false);setAgreed(false);}}}>
  <p>{help}</p><label className="check"><input type="checkbox" required checked={agreed} onChange={e=>setAgreed(e.target.checked)}/>{t('confirm')}</label>
  <div className="group-actions"><button disabled={disabled||!agreed}>{label}</button><button type="button" onClick={()=>{setOpen(false);setAgreed(false);}}>{t('cancelForm')}</button></div>
 </form>;
}
export function NewGroupTask({locale,disabled,create}:{locale:Locale;disabled:boolean;create:(body:unknown)=>Promise<boolean>}) {
 const t=(key:string)=>groupText(locale,key),[q,setQ]=useState(''),[places,setPlaces]=useState<Place[]>([]),[place,setPlace]=useState<Place|null>(null);
 const [loading,setLoading]=useState(false),[error,setError]=useState(false),[retry,setRetry]=useState(0);
 useEffect(()=>{
  let active=true;const controller=new AbortController();setPlaces([]);setError(false);setLoading(Boolean(q.trim()));
  const timer=setTimeout(()=>{if(!q.trim())return;api<{items:Place[]}>('/places?'+new URLSearchParams({q,limit:'10'}),{signal:controller.signal})
   .then(data=>{if(active)setPlaces(data.items);}).catch(()=>{if(active)setError(true);}).finally(()=>{if(active)setLoading(false);});},200);
  return()=>{active=false;clearTimeout(timer);controller.abort();};
 },[q,retry]);
 return <details className="group-new-task"><summary>{t('newTask')}</summary><form onSubmit={async e=>{
  e.preventDefault();if(!place)return;const form=e.currentTarget,data=new FormData(form);
  if(await create({place_id:place.id,title:data.get('title'),instructions:data.get('instructions')})){form.reset();setPlace(null);setQ('');}
 }}>
  <label>{t('placeSearch')}<input type="search" value={q} maxLength={200} onChange={e=>{setQ(e.target.value);setPlace(null);}}/></label>
  <div className="group-place-results" aria-label={t('placeResults')} aria-live="polite" aria-busy={loading}>
   {loading?<p>{t('loading')}</p>:error?<><p>{t('failure')}</p><button type="button" onClick={()=>setRetry(x=>x+1)}>{t('retry')}</button></>:places.map(p=><button type="button" key={p.id} aria-pressed={place?.id===p.id} onClick={()=>setPlace(p)}>{p.name} · {p.state}<small>{p.id} · {formatDataset(p.source.dataset,locale)} · {formatReferenceDate(p.source.reference_date,locale)}</small></button>)}
   {!loading&&!error&&q.trim()&&!places.length&&<p>{t('noPlaces')}</p>}
  </div>
  {place&&<p>{t('placeSelected')}: <strong>{place.name}</strong> <code>{place.id}</code></p>}
  <label>{t('title')}<input name="title" minLength={5} maxLength={160} required/></label>
  <label>{t('instructions')}<textarea name="instructions" maxLength={2000} rows={3}/></label>
  <button disabled={disabled||!place}>{t('createTask')}</button>
 </form></details>;
}
export function SubmitGroupTask({locale,placeId,disabled,submit}:{locale:Locale;placeId:string;disabled:boolean;submit:(body:Submission)=>Promise<boolean>}) {
 const prefix=useId();
 const t=(key:string)=>groupText(locale,key),[rows,setRows]=useState<Observation[]>([]),[selection,setSelection]=useState('');
 const [loading,setLoading]=useState(true),[retry,setRetry]=useState(0),[error,setError]=useState(''),[saving,setSaving]=useState(false),[notice,setNotice]=useState('');
 const [consent,setConsent]=useState(false),alive=useRef(true),lock=useRef(false);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{let active=true;const controller=new AbortController();setLoading(true);setError('');
  api<Observation[]>('/observations/mine',{signal:controller.signal}).then(values=>{if(active){const eligible=ownObservations(values,placeId);setRows(eligible);setSelection(old=>eligible.some((row:Observation)=>row.id===old)?old:'');}})
   .catch(e=>{if(active)setError(groupFailure(e));}).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;controller.abort();};
 },[placeId,retry]);
 return <div className="group-submission">
  <p>{t('privateObservation')}</p>
  <form onSubmit={async e=>{e.preventDefault();if(selection&&consent&&await submit({action:'submit',observation_id:selection,share_with_group:true}))setConsent(false);}}>
   <label htmlFor={prefix+'-observation'}>{t('selectObservation')}</label>
   <select id={prefix+'-observation'} value={selection} required disabled={loading||disabled} onChange={e=>{setSelection(e.target.value);setConsent(false);}}><option value="">{t('choose')}</option>{rows.map(row=><option key={row.id} value={row.id}>{row.observation.observed_on} · {row.observation.body.slice(0,100)}</option>)}</select>
   {loading?<p>{t('loading')}</p>:!rows.length&&!error&&<p>{t('noObservations')}</p>}
   {error&&<p role="status">{t(error)}</p>}
   <button type="button" onClick={()=>setRetry(x=>x+1)} disabled={loading||saving}>{t('refreshObservations')}</button>
   {rows.find(row=>row.id===selection)&&<p className="group-observation-preview">{rows.find(row=>row.id===selection)!.observation.body}</p>}
   <label className="check"><input type="checkbox" required checked={consent} onChange={e=>setConsent(e.target.checked)}/>{t('shareConsent')}</label>
   <button disabled={disabled||!selection||!consent||saving}>{t('submit')}</button>
  </form>
  <details><summary>{t('newObservation')}</summary><p>{t('onlyPublicArea')}</p>
   <form onSubmit={async e=>{
    e.preventDefault();if(lock.current)return;lock.current=true;setSaving(true);setNotice('');setError('');const form=e.currentTarget,data=new FormData(form);
    try{const row=await api<{id:string}>('/observations',{method:'POST',body:JSON.stringify({place_id:placeId,mode:'field',observed_on:data.get('observed_on'),body:data.get('body'),consent:data.get('consent')==='on'})});
     if(alive.current){form.reset();setSelection(row.id);setRetry(x=>x+1);setNotice('observationSaved');setConsent(false);}
    }catch(err){if(alive.current)setError(groupFailure(err));}finally{lock.current=false;if(alive.current)setSaving(false);}
   }}>
    <label>{t('observedOn')}<input type="date" name="observed_on" required max={new Date().toISOString().slice(0,10)}/></label>
    <label>{t('body')}<textarea name="body" minLength={20} maxLength={1200} rows={4} required/></label>
    <label className="check"><input name="consent" type="checkbox" required/>{t('observationConsent')}</label>
    <button disabled={disabled||saving}>{t('saveObservation')}</button>
   </form>
  </details>
  {notice&&<p role="status">{t(notice)}</p>}
 </div>;
}
