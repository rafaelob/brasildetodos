// SPDX-License-Identifier: AGPL-3.0-or-later
import {useEffect,useId,useState} from 'react';
import type {ReactNode} from 'react';
import {api} from './api';
import {safeReference} from './i18n.mjs';
import {regionParameters} from './region-text.mjs';
import Resources from './Resources';
import type {Locale,Money,Source} from './types';
import './region.css';
type Town={id:string;name:string;state:string;source?:Source|null};
type Directory={items:Town[];total:number;has_more:boolean};
type Summary={municipality:Town;generated_at:string;service_records:number;resource_records:number;services:{kind:string;records:number;with_geometry:number;without_geometry:number}[];resource_groups:{source_id:string;territorial_basis:string;records:number}[]};
type Financial={events:Money[];total:number;truncated:boolean};
const states='AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' ');
export default function Region({initialId='',locale,t,onExplore,renderMoney}:{initialId?:string;locale:Locale;t:(key:string)=>string;onExplore:(town:string,kind:string)=>void;renderMoney:(events:Money[])=>ReactNode}){
 const prefix=useId();
 const [q,setQ]=useState(''),[state,setState]=useState(''),[page,setPage]=useState(1),[retry,setRetry]=useState(0);
 const [directory,setDirectory]=useState<Directory|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(false);
 const [selected,setSelected]=useState(initialId),[summary,setSummary]=useState<Summary|null>(null),[summaryLoading,setSummaryLoading]=useState(false),[summaryError,setSummaryError]=useState(false),[summaryRetry,setSummaryRetry]=useState(0);
 const [financeOpen,setFinanceOpen]=useState(false),[finance,setFinance]=useState<Financial|null>(null),[financeError,setFinanceError]=useState(false),[financeRetry,setFinanceRetry]=useState(0);
 useEffect(()=>setSelected(initialId),[initialId]);
 useEffect(()=>{const control=new AbortController();let current=true;setLoading(true);setError(false);setDirectory(null);
  const timer=setTimeout(()=>api<Directory>('/territories/search?'+regionParameters(q,state,page),{signal:control.signal}).then(value=>{if(current)setDirectory(value);}).catch(()=>{if(current)setError(true);}).finally(()=>{if(current)setLoading(false);}),180);
  return()=>{current=false;clearTimeout(timer);control.abort();};},[q,state,page,retry]);
 useEffect(()=>{const control=new AbortController();let current=true;setSummary(null);setSummaryError(false);setFinanceOpen(false);setFinance(null);setFinanceError(false);
  if(!selected){setSummaryLoading(false);return()=>control.abort();}setSummaryLoading(true);
  api<Summary>('/territories/'+encodeURIComponent(selected)+'/summary',{signal:control.signal}).then(value=>{if(current)setSummary(value);}).catch(()=>{if(current)setSummaryError(true);}).finally(()=>{if(current)setSummaryLoading(false);});
  return()=>{current=false;control.abort();};},[selected,summaryRetry]);
 useEffect(()=>{if(!financeOpen||!selected)return;const control=new AbortController();let current=true;setFinance(null);setFinanceError(false);
  api<Financial>('/regions/'+encodeURIComponent(selected),{signal:control.signal}).then(value=>{if(current)setFinance(value);}).catch(()=>{if(current)setFinanceError(true);});
  return()=>{current=false;control.abort();};},[selected,financeOpen,financeRetry]);
 const n=(value:number)=>value.toLocaleString(locale);
 return <section className="page region-page"><header><span className="eyebrow">BRASIL DE TODOS</span><h1>{t('regionHeading')}</h1><p>{t('regionIntro')}</p></header>
  <div className="region-layout"><aside className="region-directory" aria-label={t('towns')}><form className="region-filters" onSubmit={event=>event.preventDefault()}><label htmlFor={prefix+'q'}>{t('regionSearch')}</label><input id={prefix+'q'} type="search" maxLength={200} value={q} onChange={event=>{setQ(event.target.value);setPage(1);}}/><label htmlFor={prefix+'state'}>{t('regionState')}</label><select id={prefix+'state'} value={state} onChange={event=>{setState(event.target.value);setPage(1);}}><option value="">{t('regionAllStates')}</option>{states.map(s=><option key={s}>{s}</option>)}</select></form>
   <p className="quiet">{t('regionDirectoryNote')}</p><div aria-live="polite" aria-busy={loading}>{loading?<p>{t('loading')}</p>:error?<div role="status"><p>{t('failure')}</p><button onClick={()=>setRetry(v=>v+1)}>{t('regionRetry')}</button></div>:<><p>{n(directory?.total||0)} {t('towns')}</p>{directory?.items.length?directory.items.map(town=><button key={town.id} className="region-town" aria-pressed={selected===town.id} onClick={()=>setSelected(town.id)}><strong>{town.name} · {town.state}</strong><small>{town.id}</small></button>):<p>{t('regionNoMatch')}</p>}<div className="pager"><button disabled={page===1} onClick={()=>setPage(v=>v-1)}>{t('regionPrev')}</button><span>{page}</span><button disabled={!directory?.has_more} onClick={()=>setPage(v=>v+1)}>{t('regionNext')}</button></div></>}</div></aside>
   <div className="region-content" aria-live="polite" aria-busy={summaryLoading}>{!selected?<p className="empty">{t('regionSelect')}</p>:summaryLoading?<p>{t('loading')}</p>:summaryError?<div className="panel" role="status"><p>{t('failure')}</p><button onClick={()=>setSummaryRetry(v=>v+1)}>{t('regionSummaryRetry')}</button></div>:summary&&<><h2>{summary.municipality.name} · {summary.municipality.state}</h2><p className="quiet">{summary.municipality.id} · {t('regionCurrent')}: {new Date(summary.generated_at).toLocaleString(locale)}</p><p className="callout">{t('regionResourceNote')}</p>
    <h3>{t('regionLoaded')}</h3>{!summary.service_records&&<p>{t('regionNoServices')}</p>}<div className="region-metrics">{summary.services.map(item=><article className="panel region-metric" key={item.kind}><h4>{t(item.kind)}</h4><strong>{n(item.records)}</strong><dl><dt>{t('regionGeometry')}</dt><dd>{n(item.with_geometry)}</dd><dt>{t('regionNoGeometry')}</dt><dd>{n(item.without_geometry)}</dd></dl><button onClick={()=>onExplore(selected,item.kind)}>{t('regionExplore')} · {t(item.kind)}</button></article>)}</div>
    {summary.municipality.source&&<details className="source"><summary>{t('regionSource')}</summary><p>{summary.municipality.source.dataset}</p><p>{t('reference')}: {summary.municipality.source.reference_date||t('unknown')}</p><p>{t('collected')}: {summary.municipality.source.collected_at}</p>{safeReference(summary.municipality.source.url)&&<a href={safeReference(summary.municipality.source.url)!} target="_blank" rel="noopener noreferrer">{t('sourceOriginal')} ↗</a>}<p><code>{summary.municipality.source.snapshot_sha256}</code></p></details>}
    <h3>{t('regionResourceCount')}: {n(summary.resource_records)}</h3>{summary.resource_groups.map(item=><p key={item.source_id+item.territorial_basis}>{item.source_id} · {n(item.records)} {t('regionRecords')} · {t(item.territorial_basis==='buyer_registered_municipality'?'regionBuyer':'regionTerritorial')}</p>)}{!summary.resource_records&&<p>{t('regionNoResources')}</p>}
    <Resources municipalityId={selected} t={t} locale={locale}/><section className="region-finance"><h3>{t('regionFinance')}</h3><p>{t('regionFinanceNote')}</p>{!financeOpen?<button onClick={()=>setFinanceOpen(true)}>{t('regionFinanceLoad')}</button>:financeError?<><p>{t('failure')}</p><button onClick={()=>setFinanceRetry(v=>v+1)}>{t('retry')}</button></>:!finance?<p>{t('loading')}</p>:<><p>{n(finance.events.length)} / {n(finance.total)} {t('regionRecords')}{finance.truncated?' · '+t('truncated'):''}</p>{renderMoney(finance.events)}</>}</section>
   </>}</div></div></section>;
}
