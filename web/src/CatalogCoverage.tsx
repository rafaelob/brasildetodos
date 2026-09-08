// SPDX-License-Identifier: AGPL-3.0-or-later
import {useEffect,useState} from 'react';
import {api} from './api';
import {safeReference} from './i18n.mjs';
import {watchDate} from './watch-state.mjs';
import {SOURCE_IDS,STATUS_IDS,STATE_IDS,sourceLabel,statusLabel,coverageCount,partitionSelection} from './coverage-text.mjs';
import type {Locale} from './types';
import './coverage.css';

type T=(key:string)=>string;
type Run={id:string;source_id:string;status:string;started_at:string|null;finished_at:string|null;reference_date:string|null;counts:Record<string,number|null>};
type Partition={source_id:string;state:string;records:number;geocoded:number;without_geometry:number};
type Coverage={generated_at:string;summary:{places:number;geocoded:number;without_geometry:number;resources:number};sources:{id:string;data_state:string;documentation_url:string|null;places:number;resources:number;last_attempt:Run|null}[];partitions:Partition[]};
type Imports={items:Run[];total:number;page:number;has_more:boolean};

function ImportHistory({locale,t}:{locale:Locale;t:T}){
 const [source,setSource]=useState('all'),[status,setStatus]=useState('all'),[page,setPage]=useState(1),[refresh,setRefresh]=useState(0);
 const [response,setResponse]=useState<{key:string;data:Imports}|null>(null),[error,setError]=useState(false),[loading,setLoading]=useState(true);
 const key=new URLSearchParams({source,status,page:String(page),limit:'5'}).toString();
 const data=response?.key===key?response.data:null;
 useEffect(()=>{const controller=new AbortController();setLoading(true);setError(false);
  api<Imports>('/imports?'+key,{signal:controller.signal}).then(data=>{if(!controller.signal.aborted){setResponse({key,data});setLoading(false);}}).catch(()=>{if(!controller.signal.aborted){setError(true);setLoading(false);}});
  return()=>controller.abort();
 },[key,refresh]);
 return <section className="coverage-history" aria-labelledby="import-history-title"><h2 id="import-history-title">{t('coverageImports')}</h2>
  <p>{t('coverageNeverComplete')}</p>
  <div className="coverage-filters"><label>{t('coverageImportSource')}<select aria-label={t('coverageImportSource')} value={source} onChange={e=>{setSource(e.target.value);setPage(1);}}><option value="all">{t('coverageAll')}</option>{SOURCE_IDS.map(id=><option value={id} key={id}>{sourceLabel(id,t)}</option>)}</select></label>
  <label>{t('coverageImportStatus')}<select aria-label={t('coverageImportStatus')} value={status} onChange={e=>{setStatus(e.target.value);setPage(1);}}><option value="all">{t('coverageAll')}</option>{STATUS_IDS.map(id=><option value={id} key={id}>{statusLabel(id,t)}</option>)}</select></label></div>
  <div role="status" aria-live="polite">{loading?t('loading'):error?t('coverageImportsError'):null}</div>
  {error&&<button onClick={()=>setRefresh(v=>v+1)}>{t('coverageImportsRetry')}</button>}
  {!loading&&!error&&data?.items.length===0&&<p>{t('coverageImportsEmpty')}</p>}
  <div className="coverage-run-list" aria-busy={loading}>{data?.items.map(run=><article key={run.id} className={'coverage-run coverage-run-'+run.status}>
   <header><h3>{sourceLabel(run.source_id,t)}</h3><span className="pill">{statusLabel(run.status,t)}</span></header>
   <dl><div><dt>{t('coverageAttemptDate')}</dt><dd>{watchDate(run.started_at,locale,t)}</dd></div><div><dt>{t('coverageReference')}</dt><dd>{run.reference_date||t('unknown')}</dd></div>
   {[['read','coverageRead'],['created','coverageCreated'],['updated','coverageUpdated']].map(([key,label])=><div key={key}><dt>{t(label)}</dt><dd>{coverageCount(run.counts[key],locale,t)}</dd></div>)}</dl>
   {run.status==='failed'&&<p className="callout">{t('coverageFailedNote')}</p>}
  </article>)}</div>
  {data&&<nav className="pager" aria-label={t('coverageHistoryPage')}><button disabled={page===1||loading} onClick={()=>setPage(v=>v-1)}>{t('prev')}</button><span>{page} · {coverageCount(data.total,locale,t)} {t('runs')}</span><button disabled={!data.has_more||loading} onClick={()=>setPage(v=>v+1)}>{t('next')}</button></nav>}
 </section>;
}

export default function CatalogCoverage({locale,t}:{locale:Locale;t:T}){
 const [data,setData]=useState<Coverage|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(false),[refresh,setRefresh]=useState(0);
 const [source,setSource]=useState('all'),[state,setState]=useState('all');
 useEffect(()=>{const controller=new AbortController();setLoading(true);setError(false);
  api<Coverage>('/coverage',{signal:controller.signal}).then(value=>{if(!controller.signal.aborted){setData(value);setLoading(false);}}).catch(()=>{if(!controller.signal.aborted){setError(true);setLoading(false);}});
  return()=>controller.abort();
 },[refresh]);
 const rows=data?partitionSelection(data.partitions,source,state):[];
 return <section className="page coverage-page" aria-labelledby="coverage-title">
  <header className="coverage-heading"><div><h1 id="coverage-title">{t('coverageTitle')}</h1><p>{t('coverageIntro')}</p></div><button disabled={loading} onClick={()=>setRefresh(v=>v+1)}>{t('coverageRefresh')}</button></header>
  <p className="callout">{t('coverageScope')}</p>
  <div aria-live="polite" role="status">{loading?t('loading'):error?t('coverageError'):null}</div>
  {error&&<button onClick={()=>setRefresh(v=>v+1)}>{t('coverageRetry')}</button>}
  {data&&<><p className="quiet">{t('coverageObservedAt')}: <time dateTime={data.generated_at}>{watchDate(data.generated_at,locale,t)}</time></p>
   <div className="coverage-metrics">{[['places','coveragePlaces'],['geocoded','coverageLocated'],['without_geometry','coverageUnlocated'],['resources','coverageResources']].map(([key,label])=><div className="coverage-metric" key={key}><span>{t(label)}</span><strong>{coverageCount(data.summary[key as keyof Coverage['summary']],locale,t)}</strong></div>)}</div>
   <h2>{t('coverageSources')}</h2><div className="coverage-sources">{data.sources.map(item=>{const url=safeReference(item.documentation_url);return <article key={item.id} className="coverage-source"><h3>{sourceLabel(item.id,t)}</h3><p className="pill">{t(item.data_state==='loaded'?'coverageLoaded':'coverageNotLoaded')}</p><p>{coverageCount(item.places,locale,t)} {t('coveragePlaces')} · {coverageCount(item.resources,locale,t)} {t('coverageResources')}</p><p>{item.last_attempt?<>{t('coverageLastAttempt')}: {statusLabel(item.last_attempt.status,t)} · {watchDate(item.last_attempt.started_at,locale,t)}</>:t('coverageNoAttempt')}</p>{url&&<a href={url} target="_blank" rel="noopener noreferrer">{t('coverageDocumentation')} ↗</a>}</article>;})}</div>
   <details className="coverage-territory"><summary>{t('coverageMore')}</summary><h2>{t('coverageTerritory')}</h2>
    <div className="coverage-filters"><label>{t('coverageSourceFilter')}<select aria-label={t('coverageSourceFilter')} value={source} onChange={e=>setSource(e.target.value)}><option value="all">{t('coverageAll')}</option>{SOURCE_IDS.map(id=><option key={id} value={id}>{sourceLabel(id,t)}</option>)}</select></label>
    <label>{t('coverageStateFilter')}<select aria-label={t('coverageStateFilter')} value={state} onChange={e=>setState(e.target.value)}><option value="all">{t('coverageAll')}</option>{STATE_IDS.map(id=><option key={id}>{id}</option>)}<option value="unknown">{t('coverageUnknownState')}</option></select></label></div>
    {rows.length?<div className="table-scroll"><table><caption>{t('coverageTerritory')}</caption><thead><tr>{['source','coverageState','coverageRecords','coverageLocated','coverageUnlocated'].map(key=><th key={key} scope="col">{t(key)}</th>)}</tr></thead><tbody>{rows.map((row:Partition)=><tr key={row.source_id+row.state}><th scope="row">{sourceLabel(row.source_id,t)}</th><td>{row.state==='unknown'?t('coverageUnknownState'):row.state}</td><td>{coverageCount(row.records,locale,t)}</td><td>{coverageCount(row.geocoded,locale,t)}</td><td>{coverageCount(row.without_geometry,locale,t)}</td></tr>)}</tbody></table></div>:<p>{t('coverageNoPartitions')}</p>}
   </details>
  </>}
  <ImportHistory locale={locale} t={t}/>
 </section>;
}
