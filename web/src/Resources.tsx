import {ResourceCoverage,CollectionDownloads} from './ResourceStatus';
import {useEffect,useState,useId} from 'react';
import {api} from './api';
import {ShareResource,ResourceDownloads} from './ResourceActions';
import {parseResourceRoute,normalizeResourceRoute} from './resource-route.mjs';
import './resources.css';
import {money,safeReference} from './i18n.mjs';
import {resourceAmounts,resourceAmountText} from './resource-i18n.mjs';
import type {Locale,Source} from './types';

type T=(key:string)=>string;
export type PublicResource={id:string;kind:string;title:string;municipality_id:string|null;source:Source;attributes:Record<string,unknown>};
type Versions={total:number;page:number;limit:number;versions:{revision:number;observed_at:string;changed_fields:string[];resource:PublicResource}[]};
const providers=['pncp_contracts','transferegov_special_plans','obrasgov_projects'];
const states='AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' ');
const scopes:Record<string,string>={buyer_registered_municipality_not_execution:'resourceBuyerScope',
  beneficiary_municipality_not_resolved:'resourceUnresolvedScope',state_only_municipality_unresolved:'resourceStateScope'};

function Provenance({source,t}:{source:Source;t:T}) {
  const url=safeReference(source.url);
  return <div className="source"><strong>{t(source.dataset)}</strong><dl>
    <dt>{t('reference')}</dt><dd>{source.reference_date||t('unknown')}</dd>
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
    <h2>{row.title}</h2><code>{row.id}</code>
    <p className="callout">{t(scopes[String(a.territorial_basis)]||'resourceScope')}</p>
    {a.profile==='transferegov_special_plans'&&<p>{t('resourceProposalNotice')}</p>}
    {a.budget_direction==='revenue'&&<p className="callout">{t('resourceRevenue')}</p>}
    {a.budget_direction==='unknown'&&<p>{t('resourceUnknownDirection')}</p>}
    <dl>{[['declared_status','resourceStatus'],['buyer_name','resourceBuyer'],['upstream_updated_at','resourceOfficialUpdate'],
      ['starts_on','resourceStart'],['ends_on','resourceEnd']].map(([key,label])=>typeof a[key]==='string'
        ? <div className="resource-fact" key={key}><dt>{t(label)}</dt><dd>{String(a[key])}</dd></div>:null)}</dl>
    {amounts.length||planned.length?<><p>{t('resourceNotPayment')}</p><div className="money-grid">
      {amounts.map(item=><div className="money" key={item.key}><span>{t(item.label)}</span><h3>{resourceAmountText(item,locale)}</h3></div>)}
      {planned.map((entry,index)=><div className="money" key={index}><span>{t('resourceProjectAmount')}</span>
        <h3>{money(Number(entry.planned_cents),locale)}</h3><p>{typeof entry.source_name==='string'?entry.source_name:t('unknown')}</p></div>)}
    </div></>:<p>{t('resourceNoAmount')}</p>}
    {amounts.some(item=>'decimal' in item)&&<p className="callout">{t('resourcePrecision')}</p>}
    <Provenance source={row.source} t={t}/>
    <div className="resource-actions"><ShareResource criteria={{id:row.id,locale}} t={t} label="resourceShareRecord"/><ResourceDownloads id={row.id} locale={locale} t={t}/></div>
    <button aria-expanded={show} onClick={()=>setShow(value=>!value)}>{t(show?'resourceHistoryClose':'resourceHistory')}</button>
    {show&&<section aria-label={t('resourceHistory')}><p>{t('resourceHistoryNotice')}</p>
      {error?<div role="status"><p>{t('failure')}</p><button onClick={()=>setAttempt(value=>value+1)}>{t('resourceRetry')}</button></div>
        :history===null?<p role="status">{t('loading')}</p>:history.total===0?<p>{t('resourceHistoryEmpty')}</p>
        :<>{history.versions.map(version=><article className="source" key={version.revision}>
          <h3>{t('resourceRevision')} {version.revision}</h3>
          <p>{t('resourceCaptured')}: {version.observed_at}</p>
          <p>{version.revision===1?t('resourceInitial'):t('resourceChanges')+': '+version.changed_fields.join(', ')}</p>
          <dl>{resourceAmounts(version.resource.attributes).map(item=><div className="resource-fact" key={item.key}><dt>{t(item.label)}</dt><dd>{resourceAmountText(item,locale)}</dd></div>)}</dl>
          <Provenance source={version.resource.source} t={t}/><ResourceDownloads id={row.id} locale={locale} t={t} revision={version.revision}/>
        </article>)}<div className="pager"><button disabled={page===1} onClick={()=>setPage(value=>value-1)}>{t('prev')}</button>
          <span>{page}</span><button disabled={page*5>=history.total} onClick={()=>setPage(value=>value+1)}>{t('next')}</button></div></>}
    </section>}
  </article>;
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
          {data.items.length?data.items.map(row=><ResourceCard key={row.id} row={row} t={t} locale={locale}/>):
            <div className="empty"><h2>{t('resourceNoResults')}</h2><p>{t('resourceNoResultsHelp')}</p><button onClick={clear}>{t('resourceClear')}</button></div>}
          {!focus&&<div className="pager"><button disabled={page===1} onClick={()=>setPage(value=>value-1)}>{t('prev')}</button><span>{page}</span>
            <button disabled={page*10>=data.total} onClick={()=>setPage(value=>value+1)}>{t('next')}</button></div>}
        </>}
    </div>
  </section>;
}
