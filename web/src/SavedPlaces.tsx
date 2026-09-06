// SPDX-License-Identifier: AGPL-3.0-or-later
import {useEffect,useState} from 'react';
import {api} from './api';
import {safeReference} from './i18n.mjs';
import {watchDate,watchPage,watchValue} from './watch-state.mjs';
import type {Locale,Place,Source} from './types';
import './watch.css';

type T=(key:string)=>string;
type Version={id:string;recorded_at:string|null;type:'started'|'updated'|'source_revision';source:Source;previous_source:Source|null;fields:{key:string;before:unknown;after:unknown}[]};
type SummaryItem={id:string;status:'available'|'outside_current_profile'|'not_found'|'unavailable';place:Place|null;
 history:{total_versions:number;included:number;truncated:boolean;first_recorded_at:string|null;versions:Version[]}|null};
type Summary={generated_at:string;items:SummaryItem[]};

function VersionEntry({entry,locale,t}:{entry:Version;locale:Locale;t:T}){
 const source=safeReference(entry.source.url);
 const previous=entry.previous_source? safeReference(entry.previous_source.url):null;
 return <li className="watch-version"><div className="watch-version-heading"><strong>{t(entry.type==='started'?'watchStarted':entry.type==='updated'?'watchChanged':'watchSourceRevision')}</strong><time dateTime={entry.recorded_at||undefined}>{watchDate(entry.recorded_at,locale,t)}</time></div>
  {entry.type==='started'&&<p>{t('watchStartedNote')}</p>}
  {entry.fields.length>0&&<details><summary>{t('watchCompare')}</summary><dl className="watch-diff">{entry.fields.map(field=><div key={field.key}><dt>{t('watchField.'+field.key)}</dt><dd><span>{t('watchBefore')}</span>{watchValue(field.before,locale,t)}</dd><dd><span>{t('watchAfter')}</span>{watchValue(field.after,locale,t)}</dd></div>)}</dl></details>}
  <p className="watch-source">{entry.source.dataset} · {t('reference')}: {entry.source.reference_date||t('unknown')} {source&&<a href={source} target="_blank" rel="noopener noreferrer">{t('sourceOriginal')} ↗</a>}</p>
  {entry.previous_source&&<p className="watch-source">{t('watchPreviousSource')}: {entry.previous_source.dataset} · {entry.previous_source.reference_date||t('unknown')} {previous&&<a href={previous} target="_blank" rel="noopener noreferrer">{t('sourceOriginal')} ↗</a>}</p>}
 </li>;
}

export default function SavedPlaces({ids,locale,t,onSelect,onRemove,onExplore}:{ids:string[];locale:Locale;t:T;onSelect:(id:string)=>void;onRemove:(id:string)=>void;onExplore:()=>void}){
 const [page,setPage]=useState(1),[refresh,setRefresh]=useState(0),[response,setResult]=useState<{key:string;data:Summary}|null>(null),[error,setError]=useState(false),[loading,setLoading]=useState(false);
 const selection=watchPage(ids,page),key=JSON.stringify(selection.ids);
 const result=response?.key===key?response.data:null;
 useEffect(()=>{
  const controller=new AbortController();setResult(null);setError(false);
  if(!selection.ids.length){setLoading(false);return()=>controller.abort();}
  setLoading(true);
  api<Summary>('/saved-places/summary',{method:'POST',body:JSON.stringify({place_ids:selection.ids,versions_per_place:3}),signal:controller.signal})
   .then(value=>{if(!controller.signal.aborted){setResult({key,data:value});setLoading(false);}})
   .catch(()=>{if(!controller.signal.aborted){setError(true);setLoading(false);}});
  return()=>controller.abort();
 },[key,refresh]);
 return <section className="page watch-page" aria-labelledby="watch-title">
  <header className="watch-heading"><div><h1 id="watch-title">{t('watchTitle')}</h1><p>{t('watchIntro')}</p></div>{selection.total>0&&<button disabled={loading} onClick={()=>setRefresh(v=>v+1)}>{t('watchRefresh')}</button>}</header>
  <p className="callout">{t('watchPrivacy')}</p>
  {selection.total===0?<div className="watch-empty"><span aria-hidden="true">☆</span><h2>{t('watchEmptyTitle')}</h2><p>{t('watchEmptyBody')}</p><button className="primary" onClick={onExplore}>{t('watchExplore')}</button></div>:<>
   <p>{selection.total.toLocaleString(locale)} {t('watchCount')}</p><p className="quiet">{t('watchHint')}</p>
   <div aria-live="polite" role="status" className="watch-status">{loading?t('loading'):error?t('watchFailure'):result?<>{t('watchUpdated')}: {watchDate(result.generated_at,locale,t)}</>:null}</div>
   {error&&<button onClick={()=>setRefresh(v=>v+1)}>{t('watchRetry')}</button>}
   <div className="watch-grid" aria-busy={loading}>
   {result?.items.map(item=><article className="watch-card" key={item.id}>
     <div className="watch-card-top"><div><span className="eyebrow">{item.place?`${t(item.place.kind)} · ${item.place.state}`:t('unknown')}</span><h2>{item.place?.name||item.id}</h2></div><button className="watch-remove" onClick={()=>onRemove(item.id)} aria-label={t('watchRemove')+' '+(item.place?.name||item.id)}>★ <span>{t('watchRemove')}</span></button></div>
     {item.place?<><p>{item.place.address||t('noAddress')}</p>{item.status==='outside_current_profile'&&<p className="watch-warning">{t('withdrawn')}</p>}{item.place.latitude===null&&<p className="quiet">{t('noGeo')}</p>}
       <p className="watch-source">{item.place.source.dataset} · {t('reference')}: {item.place.source.reference_date||t('unknown')}</p>
       <button className="primary" onClick={()=>onSelect(item.id)}>{t('watchDetails')}</button>
       <section className="watch-history" aria-label={t('watchLatest')}><h3>{t('watchLatest')} <span>{item.history?.total_versions.toLocaleString(locale)} {t('watchVersions')}</span></h3>
         {item.history?.versions.length?<ol>{item.history.versions.map(entry=><VersionEntry key={entry.id} entry={entry} locale={locale} t={t}/>)}</ol>:<p>{t('watchNoHistory')}</p>}
         {item.history?.truncated&&<p className="watch-warning">{t('watchTruncated')}</p>}
       </section>
     </>:<><p className="watch-warning">{t(item.status==='not_found'?'watchMissing':'watchUnavailable')}</p><p>{t('watchMissingNote')}</p></>}
    </article>)}
   </div>
   {selection.pages>1&&<nav className="pager" aria-label={t('watchPage')}><button disabled={selection.page===1||loading} onClick={()=>setPage(selection.page-1)}>{t('prev')}</button><span>{selection.page} / {selection.pages}</span><button disabled={selection.page===selection.pages||loading} onClick={()=>setPage(selection.page+1)}>{t('next')}</button></nav>}
  </>}
 </section>;
}
