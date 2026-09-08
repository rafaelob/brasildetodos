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
function AuditCoverage({services,t,locale}:{services:Summary['services'];t:(key:string)=>string;locale:Locale}){
 if(!services||services.length===0)return null;
 return <div className="region-audit-dashboard panel">
  <h4>{t('regionAuditTitle')}</h4><p className="quiet">{t('regionAuditNote')}</p>
  <div className="region-audit-grid">{services.map(item=>{
   const pct=item.records>0?Math.round((item.with_geometry/item.records)*100):0;
   return <div className="region-audit-item" key={item.kind}>
    <div className="region-audit-labels"><strong>{t(item.kind)}</strong><span>{pct}% {t('regionGeoRate')}</span></div>
    <div className="region-progress-track" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
     <div className="region-progress-fill" style={{width:`${pct}%`}}></div>
    </div>
    <small>{item.with_geometry.toLocaleString(locale)} / {item.records.toLocaleString(locale)} {t('regionRecords')}</small>
   </div>;
  })}</div></div>;
}

function ResourceDistribution({groups,total,t,locale}:{groups:Summary['resource_groups'];total:number;t:(key:string)=>string;locale:Locale}){
 if(!groups||groups.length===0||total===0)return null;
 const bySource:Record<string,number>={};
 for(const g of groups)bySource[g.source_id]=(bySource[g.source_id]||0)+g.records;
 const entries=Object.entries(bySource);
 const colors:Record<string,string>={obrasgov_projects:'#198754',pncp_contracts:'#0d6efd',transferegov_special_plans:'#fd7e14'};
 return <div className="region-resource-dist panel">
  <h4>{t('regionResourceDestTitle')}</h4>
  <div className="region-stacked-bar">{entries.map(([src,count])=>{
   const pct=Math.max(1,Math.round((count/total)*100));
   return <div key={src} className="region-stacked-segment" style={{width:`${pct}%`,backgroundColor:colors[src]||'#6c757d'}} title={`${t(src)||src}: ${count} (${pct}%)`}></div>;
  })}</div>
  <div className="region-dist-legend">{entries.map(([src,count])=>{
   const pct=Math.round((count/total)*100);
   return <div className="region-dist-legend-item" key={src}>
    <span className="region-legend-dot" style={{backgroundColor:colors[src]||'#6c757d'}}></span>
    <span>{t(src)||src}: <strong>{count.toLocaleString(locale)}</strong> ({pct}%)</span>
   </div>;
  })}</div></div>;
}

function FinancialTimeline({events,t,locale}:{events:Money[];t:(key:string)=>string;locale:Locale}){
 if(!events||events.length===0)return null;
 const byYear:Record<string,number>={};
 for(const ev of events){const y=ev.period?ev.period.slice(0,4):t('unknown');byYear[y]=(byYear[y]||0)+1;}
 const sortedYears=Object.entries(byYear).sort((a,b)=>b[0].localeCompare(a[0]));
 const maxCount=Math.max(...Object.values(byYear),1);
 return <div className="region-timeline panel">
  <h4>{t('regionTimelineTitle')}</h4><p className="quiet">{t('regionTimelineNote')}</p>
  <div className="region-timeline-rows">{sortedYears.map(([year,count])=>{
   const pct=Math.round((count/maxCount)*100);
   return <div className="region-timeline-row" key={year}>
    <span className="region-timeline-year"><strong>{year}</strong></span>
    <div className="region-timeline-track"><div className="region-timeline-fill" style={{width:`${pct}%`}}></div></div>
    <span className="region-timeline-count">{count.toLocaleString(locale)} {t('regionEvents')}</span>
   </div>;
  })}</div></div>;
}

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
    <AuditCoverage services={summary.services} t={t} locale={locale}/>
    {summary.municipality.source&&<details className="source"><summary>{t('regionSource')}</summary><p>{summary.municipality.source.dataset}</p><p>{t('reference')}: {summary.municipality.source.reference_date||t('unknown')}</p><p>{t('collected')}: {summary.municipality.source.collected_at}</p>{safeReference(summary.municipality.source.url)&&<a href={safeReference(summary.municipality.source.url)!} target="_blank" rel="noopener noreferrer">{t('sourceOriginal')} ↗</a>}<p><code>{summary.municipality.source.snapshot_sha256}</code></p></details>}
    <h3>{t('regionResourceCount')}: {n(summary.resource_records)}</h3>{summary.resource_groups.map(item=><p key={item.source_id+item.territorial_basis}>{item.source_id} · {n(item.records)} {t('regionRecords')} · {t(item.territorial_basis==='buyer_registered_municipality'?'regionBuyer':'regionTerritorial')}</p>)}{!summary.resource_records&&<p>{t('regionNoResources')}</p>}
    <ResourceDistribution groups={summary.resource_groups} total={summary.resource_records} t={t} locale={locale}/>
    <Resources municipalityId={selected} t={t} locale={locale}/>
    <section className="region-finance"><h3>{t('regionFinance')}</h3><p>{t('regionFinanceNote')}</p>{!financeOpen?<button onClick={()=>setFinanceOpen(true)}>{t('regionFinanceLoad')}</button>:financeError?<><p>{t('failure')}</p><button onClick={()=>setFinanceRetry(v=>v+1)}>{t('retry')}</button></>:!finance?<p>{t('loading')}</p>:<><p>{n(finance.events.length)} / {n(finance.total)} {t('regionRecords')}{finance.truncated?' · '+t('truncated'):''}</p><FinancialTimeline events={finance.events} t={t} locale={locale}/>{renderMoney(finance.events)}</>}</section>
   </>}</div></div></section>;
}

