import {useEffect,useState} from 'react';
import {api} from './api';
import {money,safeReference} from './i18n.mjs';
import {resourceAmounts} from './resource-i18n.mjs';
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
      {amounts.map(item=><div className="money" key={item.key}><span>{t(item.label)}</span><h3>{money(item.cents,locale)}</h3></div>)}
      {planned.map((entry,index)=><div className="money" key={index}><span>{t('resourceProjectAmount')}</span>
        <h3>{money(Number(entry.planned_cents),locale)}</h3><p>{typeof entry.source_name==='string'?entry.source_name:t('unknown')}</p></div>)}
    </div></>:<p>{t('resourceNoAmount')}</p>}
    <Provenance source={row.source} t={t}/>
    <button aria-expanded={show} onClick={()=>setShow(value=>!value)}>{t(show?'resourceHistoryClose':'resourceHistory')}</button>
    {show&&<section aria-label={t('resourceHistory')}><p>{t('resourceHistoryNotice')}</p>
      {error?<div role="status"><p>{t('failure')}</p><button onClick={()=>setAttempt(value=>value+1)}>{t('resourceRetry')}</button></div>
        :history===null?<p role="status">{t('loading')}</p>:history.total===0?<p>{t('resourceHistoryEmpty')}</p>
        :<>{history.versions.map(version=><article className="source" key={version.revision}>
          <h3>{t('resourceRevision')} {version.revision}</h3>
          <p>{t('resourceCaptured')}: {version.observed_at}</p>
          <p>{version.revision===1?t('resourceInitial'):t('resourceChanges')+': '+version.changed_fields.join(', ')}</p>
          <dl>{resourceAmounts(version.resource.attributes).map(item=><div className="resource-fact" key={item.key}><dt>{t(item.label)}</dt><dd>{money(item.cents,locale)}</dd></div>)}</dl>
          <Provenance source={version.resource.source} t={t}/>
        </article>)}<div className="pager"><button disabled={page===1} onClick={()=>setPage(value=>value-1)}>{t('prev')}</button>
          <span>{page}</span><button disabled={page*5>=history.total} onClick={()=>setPage(value=>value+1)}>{t('next')}</button></div></>}
    </section>}
  </article>;
}

export default function Resources({t,locale,municipalityId}:{t:T;locale:Locale;municipalityId?:string}) {
  const [q,setQ]=useState(''),[profile,setProfile]=useState(''),[state,setState]=useState('');
  const [page,setPage]=useState(1),[data,setData]=useState<{items:PublicResource[];total:number}|null>(null);
  const [error,setError]=useState(false),[attempt,setAttempt]=useState(0);
  useEffect(()=>{setPage(1);},[municipalityId]);
  useEffect(()=>{
    const controller=new AbortController();setData(null);setError(false);
    const timer=setTimeout(()=>{
      const params=new URLSearchParams({q,profile,state,page:String(page),limit:'10'});
      if(municipalityId)params.set('municipality_id',municipalityId);
      for(const[key,value]of [...params])if(!value)params.delete(key);
      api<{items:PublicResource[];total:number}>('/resources?'+params,{signal:controller.signal})
        .then(result=>{if(!controller.signal.aborted)setData(result);})
        .catch(()=>{if(!controller.signal.aborted)setError(true);});
    },200);
    return()=>{clearTimeout(timer);controller.abort();};
  },[q,profile,state,page,municipalityId,attempt]);
  return <section className={municipalityId?'resource-region':'page'} aria-label={t('resources')}>
    {municipalityId?<h2>{t('resources')}</h2>:<h1>{t('resources')}</h1>}<p>{t('resourceIntro')}</p>
    <div className="resource-filters"><label>{t('resourceSearch')}<input type="search" value={q} maxLength={200}
      onChange={event=>{setQ(event.target.value);setPage(1);}}/></label>
      <label htmlFor="resource-provider">{t('resourceProvider')}</label><select id="resource-provider" value={profile}
        onChange={event=>{setProfile(event.target.value);setPage(1);}}><option value="">{t('allResourceProviders')}</option>
        {providers.map(value=><option key={value} value={value}>{t(value)}</option>)}</select>
      {!municipalityId&&<><label htmlFor="resource-state">{t('states')}</label><select id="resource-state" value={state}
        onChange={event=>{setState(event.target.value);setPage(1);}}><option value="">{t('states')}</option>{states.map(value=><option key={value}>{value}</option>)}</select></>}
    </div>
    {error?<div role="status"><p>{t('failure')}</p><button onClick={()=>setAttempt(value=>value+1)}>{t('resourceRetry')}</button></div>
      :data===null?<p role="status">{t('loading')}</p>:<><p>{data.total.toLocaleString(locale)} {t('records')}</p>
        {data.items.length?data.items.map(row=><ResourceCard key={row.id} row={row} t={t} locale={locale}/>):<p className="empty">{t('empty')}</p>}
        <div className="pager"><button disabled={page===1} onClick={()=>setPage(value=>value-1)}>{t('prev')}</button><span>{page}</span>
          <button disabled={page*10>=data.total} onClick={()=>setPage(value=>value+1)}>{t('next')}</button></div></>}
  </section>;
}
