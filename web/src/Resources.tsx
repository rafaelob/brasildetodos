import {ResourceCoverage,CollectionDownloads} from './ResourceStatus';
import ResourceObject from './ResourceObject';
import ResourceComparison from './ResourceComparison';
import {useEffect,useState,useId} from 'react';
import {api} from './api';
import {ShareResource,ResourceDownloads} from './ResourceActions';
import {parseResourceRoute,normalizeResourceRoute} from './resource-route.mjs';
import './resources.css';
import {money,safeReference,formatDataset} from './i18n.mjs';
import {resourceAmounts,resourceAmountText} from './resource-i18n.mjs';
import {historyFields,historyText} from './resource-history.mjs';
import type {Locale,Source} from './types';

type T=(key:string)=>string;
export type PublicResource={id:string;kind:string;title:string;municipality_id:string|null;source:Source;attributes:Record<string,unknown>};
type Versions={total:number;page:number;limit:number;versions:{revision:number;observed_at:string;changed_fields:string[];resource:PublicResource}[]};
const providers=['pncp_contracts','transferegov_special_plans','obrasgov_projects'];
const states='AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' ');
const scopes:Record<string,string>={buyer_registered_municipality_not_execution:'resourceBuyerScope',
  beneficiary_municipality_not_resolved:'resourceUnresolvedScope',state_only_municipality_unresolved:'resourceStateScope'};

function Provenance({source,t,locale='pt-BR'}:{source:Source;t:T;locale?:Locale}) {
  const url=safeReference(source.url);
  return <div className="source"><strong>{formatDataset(source.dataset,locale)}</strong><dl>
    <dt>{t('reference')}</dt><dd>{source.reference_date?(t('refPrefix')+' '+source.reference_date):t('officialRecord')}</dd>
    <dt>{t('collected')}</dt><dd>{source.collected_at}</dd>
    <dt>{t('sourceRecord')}</dt><dd>{source.record_id}</dd></dl>
    {url&&<a href={url} target="_blank" rel="noopener noreferrer">{t('sourceOriginal')} ↗</a>}
    <details><summary>SHA-256</summary><code>{source.snapshot_sha256}</code></details></div>;
}

export function ResourceCard({row,t,locale}:{row:PublicResource;t:T;locale:Locale}) {
  const [show,setShow]=useState(false),[page,setPage]=useState(1),[history,setHistory]=useState<Versions|null>(null);
  const [error,setError]=useState(false),[attempt,setAttempt]=useState(0);
  useEffect(()=>{
    if(!show)return;
    const controller=new AbortController();setHistory(null);setError(false);
    api<Versions>('/resource-history/'+encodeURIComponent(row.id)+'?page='+page+'&limit=5',{signal:controller.signal})
      .then(result=>{if(!controller.signal.aborted)setHistory(result);})
      .catch(()=>{if(!controller.signal.aborted)setError(true);});
    return()=>controller.abort();
  },[show,page,row.id,attempt]);
  const a=row.attributes;
  const amounts=resourceAmounts(a);
  const investments=Array.isArray(a.planned_investments)?a.planned_investments as {planned_cents:unknown;source_name:unknown}[]:[];
  const planned=investments.filter(entry=>Number.isSafeInteger(entry.planned_cents)&&Number(entry.planned_cents)>=0);
  return <article className="panel resource-card"><span className="pill">{t('resource'+row.kind[0].toUpperCase()+row.kind.slice(1))}</span>
    <ResourceObject text={row.title} locale={locale}/><code>{row.id}</code>
    <p className="callout">{t(scopes[String(a.territorial_basis)]||'resourceScope')}</p>
    {a.profile==='transferegov_special_plans'&&<p>{t('resourceProposalNotice')}</p>}
    {a.budget_direction==='revenue'&&<p className="callout">{t('resourceRevenue')}</p>}
    {a.budget_direction==='unknown'&&<p>{t('resourceUnknownDirection')}</p>}
    {typeof a.physical_execution_percentage==='number'&&<div className="resource-execution-meter" aria-label={t('resourcePhysicalExecution')}>
      <div className="resource-execution-bar" role="progressbar" aria-valuenow={Math.round(a.physical_execution_percentage)} aria-valuemin={0} aria-valuemax={100} style={{width:`${Math.min(Math.max(a.physical_execution_percentage,0),100)}%`}}></div>
      <span className="resource-execution-text">{a.physical_execution_percentage.toFixed(1)}% {t('resourcePhysicalExecution')}</span>
    </div>}
    {Array.isArray(a.project_geometries)&&a.project_geometries.length>0&&<div className="resource-geometry-pin">
      <span className="pill geo-pill">⌖ {a.project_geometries.length} {t('resourcePinsCount')} · {t('resourceGeometriesConfirmed')}</span>
    </div>}
    <dl>{[['declared_status','resourceStatus'],['buyer_name','resourceBuyer'],['upstream_updated_at','resourceOfficialUpdate'],
      ['starts_on','resourceStart'],['ends_on','resourceEnd'],
      ['planned_starts_on','resourcePlannedStart'],['planned_ends_on','resourcePlannedEnd'],
      ['last_measurement_on','resourceLastMeasurement']].map(([key,label])=>typeof a[key]==='string'
        ? <div className="resource-fact" key={key}><dt>{t(label)}</dt><dd>{String(a[key])}</dd></div>:null)}
      {typeof a.physical_execution_percentage==='number'&&<div className="resource-fact" key="exec"><dt>{t('resourcePhysicalExecution')}</dt><dd><strong>{a.physical_execution_percentage.toFixed(1)}%</strong></dd></div>}
    </dl>
    {amounts.length||planned.length?<><p>{t('resourceNotPayment')}</p><div className="money-grid">
      {amounts.map(item=><div className="money" key={item.key}><span>{t(item.label)}</span><h3>{resourceAmountText(item,locale)}</h3></div>)}
      {planned.map((entry,index)=><div className="money" key={index}><span>{t('resourceProjectAmount')}</span>
        <h3>{money(Number(entry.planned_cents),locale)}</h3><p>{typeof entry.source_name==='string'?entry.source_name:t('unknown')}</p></div>)}
    </div></>:<p>{t('resourceNoAmount')}</p>}
    {amounts.some(item=>'decimal' in item)&&<p className="callout">{t('resourcePrecision')}</p>}
    <Provenance source={row.source} t={t} locale={locale}/>
    <div className="resource-actions"><ShareResource criteria={{id:row.id,locale}} t={t} label="resourceShareRecord"/><ResourceDownloads id={row.id} locale={locale} t={t}/></div>
    <button aria-expanded={show} onClick={()=>setShow(value=>!value)}>{t(show?'resourceHistoryClose':'resourceHistory')}</button>
    {show&&<section aria-label={t('resourceHistory')}><p>{t('resourceHistoryNotice')}</p>
      {error?<div role="status"><p>{t('failure')}</p><button onClick={()=>setAttempt(value=>value+1)}>{t('resourceRetry')}</button></div>
        :history===null?<p role="status">{t('loading')}</p>:history.total===0?<p>{t('resourceHistoryEmpty')}</p>
        :<>{history.versions.map((version,index)=><article className="source" key={version.revision}>
          <h3>{t('resourceRevision')} {version.revision}</h3>
          <p>{t('resourceCaptured')}: {version.observed_at}</p>
          {version.revision===1?<p>{t('resourceInitial')}</p>:<>
            <p>{t('resourceChanges')}:</p><ul>{historyFields(version.changed_fields,locale).map(field=><li key={field.key}>{field.label}</li>)}</ul>
            <details><summary>{historyText(locale,'technical')}</summary><ul>{version.changed_fields.map((key,index)=><li key={index}><code>{key}</code></li>)}</ul></details>
          </>}
          <dl>{resourceAmounts(version.resource.attributes).map(item=><div className="resource-fact" key={item.key}><dt>{t(item.label)}</dt><dd>{resourceAmountText(item,locale)}</dd></div>)}</dl>
          {history.versions[index+1]&&<ResourceComparison key={version.revision+'-'+locale} older={history.versions[index+1]} newer={version} locale={locale}/>}
          <Provenance source={version.resource.source} t={t}/><ResourceDownloads id={row.id} locale={locale} t={t} revision={version.revision}/>
        </article>)}<div className="pager"><button disabled={page===1} onClick={()=>setPage(value=>value-1)}>{t('prev')}</button>
          <span>{page}</span><button disabled={page*5>=history.total} onClick={()=>setPage(value=>value+1)}>{t('next')}</button></div></>}
    </section>}
  </article>;
}

function ResourceAnalyticsOverview({items,t,locale}:{items:PublicResource[];t:T;locale:Locale}){
  if(!items||items.length===0)return null;
  const worksWithExec=items.filter(item=>typeof item.attributes.physical_execution_percentage==='number');
  const statusCounts:Record<string,number>={};
  items.forEach(item=>{
    const s=String(item.attributes.declared_status||'').trim();
    if(s)statusCounts[s]=(statusCounts[s]||0)+1;
  });
  const buckets=[
    {label:'0%',min:-1,max:0},
    {label:'1-25%',min:0,max:25},
    {label:'26-50%',min:25,max:50},
    {label:'51-75%',min:50,max:75},
    {label:'76-100%',min:75,max:100},
  ];
  const bucketCounts=buckets.map(b=>{
    const count=worksWithExec.filter(item=>{
      const p=Number(item.attributes.physical_execution_percentage);
      return p>b.min&&p<=b.max;
    }).length;
    return {...b,count};
  });
  const hasAnalytics=worksWithExec.length>0||Object.keys(statusCounts).length>0;
  if(!hasAnalytics)return null;
  return <div className="resources-analytics-card panel" aria-label={t('resourceAnalyticsTitle')}>
    <h3>{t('resourceAnalyticsTitle')}</h3>
    <div className="resources-analytics-grid">
      {Object.keys(statusCounts).length>0&&<div className="resources-analytics-col">
        <h4>{t('resourceStatusDist')}</h4>
        <div className="resources-status-pills">
          {Object.entries(statusCounts).map(([status,count])=><span className="pill status-pill" key={status}>
            <strong>{status}</strong>: {count.toLocaleString(locale)}
          </span>)}
        </div>
      </div>}
      {worksWithExec.length>0&&<div className="resources-analytics-col">
        <h4>{t('resourceExecBuckets')} ({worksWithExec.length.toLocaleString(locale)} {t('resourceWorksWithExec')})</h4>
        <div className="resources-bucket-bars">
          {bucketCounts.map(b=>{
            const pct=worksWithExec.length>0?Math.round((b.count/worksWithExec.length)*100):0;
            return <div className="resources-bucket-row" key={b.label}>
              <span className="resources-bucket-label">{b.label}</span>
              <div className="resources-bucket-track" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
                <div className="resources-bucket-fill" style={{width:`${pct}%`}}></div>
              </div>
              <span className="resources-bucket-count">{b.count} ({pct}%)</span>
            </div>;
          })}
        </div>
      </div>}
    </div>
  </div>;
}

export default function Resources({t,locale,municipalityId,routeHash=''}:{t:T;locale:Locale;municipalityId?:string;routeHash?:string}) {
  const incoming=normalizeResourceRoute(parseResourceRoute(routeHash)||{});
  const [q,setQ]=useState(incoming.q),[profile,setProfile]=useState(incoming.profile),[state,setState]=useState(incoming.state);
  const [focus,setFocus]=useState(incoming.id),[sharedTown,setSharedTown]=useState(incoming.municipality);
  const [page,setPage]=useState(1),[data,setData]=useState<{items:PublicResource[];total:number}|null>(null);
  const [error,setError]=useState(false),[attempt,setAttempt]=useState(0);
  const controlId=useId();const town=municipalityId||sharedTown;
  useEffect(()=>{const route=normalizeResourceRoute(parseResourceRoute(routeHash)||{});
    setQ(route.q);setProfile(route.profile);setState(route.state);setFocus(route.id);setSharedTown(route.municipality);setPage(1);
  },[routeHash]);
  useEffect(()=>{setPage(1);},[municipalityId]);
  useEffect(()=>{
    const controller=new AbortController();setData(null);setError(false);
    const timer=setTimeout(()=>{
      const params=new URLSearchParams({q,profile,state,page:String(page),limit:'10'});
      if(town)params.set('municipality_id',town);
      for(const[key,value]of [...params])if(!value)params.delete(key);
      const query=focus?api<{resource:PublicResource}>('/resource-history/'+encodeURIComponent(focus)+'?limit=1',{signal:controller.signal})
        .then(result=>({items:[result.resource],total:1}))
        :api<{items:PublicResource[];total:number}>('/resources?'+params,{signal:controller.signal});
      query.then(result=>{if(!controller.signal.aborted)setData(result);})
        .catch(()=>{if(!controller.signal.aborted)setError(true);});
    },200);
    return()=>{clearTimeout(timer);controller.abort();};
  },[q,profile,state,page,town,focus,attempt]);
  function clear(){setQ('');setProfile('');setState('');setSharedTown('');setPage(1);setFocus('');}
  return <section className={municipalityId?'resource-region':'page resources-page'} aria-label={t('resources')}>
    <header className="resource-heading"><span className="eyebrow">{t('resourceEyebrow')}</span>
      {municipalityId?<h2>{t('resources')}</h2>:<h1>{t('resources')}</h1>}<p>{t('resourceIntro')}</p></header>
    {!municipalityId&&<ResourceCoverage t={t} locale={locale}/>}
    {focus?<div className="resource-focus"><span>{t('resourceFocus')}</span><button onClick={()=>setFocus('')}>← {t('resourceBack')}</button></div>:<>
      <div className="resource-filters">
        <div className="resource-search"><label htmlFor={controlId+'-search'}>{t('resourceSearch')}</label><input id={controlId+'-search'} type="search" value={q} maxLength={200}
          onChange={event=>{setQ(event.target.value);setPage(1);}}/></div>
        <div><label htmlFor={controlId+'-provider'}>{t('resourceProvider')}</label><select id={controlId+'-provider'} value={profile}
          onChange={event=>{setProfile(event.target.value);setPage(1);}}><option value="">{t('allResourceProviders')}</option>
          {providers.map(value=><option key={value} value={value}>{t(value)}</option>)}</select></div>
        {!municipalityId&&<div><label htmlFor={controlId+'-state'}>{t('states')}</label><select id={controlId+'-state'} value={state}
          onChange={event=>{setState(event.target.value);setSharedTown('');setPage(1);}}><option value="">{t('states')}</option>{states.map(value=><option key={value}>{value}</option>)}</select></div>}
      </div>
      <div className="resource-toolbar"><button onClick={clear}>{t('resourceClear')}</button>
        <ShareResource criteria={{q,profile,state,municipality:town,locale}} t={t} label="resourceShare"/><CollectionDownloads criteria={{q,profile,state,municipality:town}} locale={locale}/></div>
      {sharedTown&&<p>{t('municipalityID')}: <code>{sharedTown}</code></p>}
    </>}
    <div aria-busy={!error&&data===null}>
      {error?<div className="empty" role="status"><p>{t(focus?'resourceFocusMissing':'failure')}</p><button onClick={()=>setAttempt(value=>value+1)}>{t('resourceRetry')}</button></div>
        :data===null?<p className="resource-loading" role="status">{t('loading')}</p>:<>
          <p className="resource-count" role="status"><strong>{data.total.toLocaleString(locale)}</strong> {t('resourceResults')}</p>
          {!focus&&<ResourceAnalyticsOverview items={data.items} t={t} locale={locale}/>}
          {data.items.length?data.items.map(row=><ResourceCard key={row.id} row={row} t={t} locale={locale}/> ):
            <div className="empty"><h2>{t('resourceNoResults')}</h2><p>{t('resourceNoResultsHelp')}</p><button onClick={clear}>{t('resourceClear')}</button></div>}
          {!focus&&<div className="pager"><button disabled={page===1} onClick={()=>setPage(value=>value-1)}>{t('prev')}</button><span>{page}</span>
            <button disabled={page*10>=data.total} onClick={()=>setPage(value=>value+1)}>{t('next')}</button></div>}
        </>}
    </div>
  </section>;
}
