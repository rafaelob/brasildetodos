// SPDX-License-Identifier: AGPL-3.0-or-later
import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import {safeReference,formatDataset,formatReferenceDate} from './i18n.mjs';
import {comparisonItems,comparisonText} from './place-comparison.mjs';
import {watchDate} from './watch-state.mjs';
import type {Locale,Place} from './types';
import './place-comparison.css';
type Item={id:string;status:string;place:Place|null};

export default function PlaceComparison({ids,locale,t,onClose,onSelect}:{ids:string[];locale:Locale;t:(key:string)=>string;onClose:()=>void;onSelect:(id:string)=>void}) {
 const words=comparisonText[locale],key=JSON.stringify(ids),heading=useRef<HTMLHeadingElement>(null);
 const [refresh,setRefresh]=useState(0),[result,setResult]=useState<{key:string;items:Item[]}|null>(null),[error,setError]=useState(false),[loading,setLoading]=useState(false);
 const items=result?.key===key?result.items:[];
 useEffect(()=>{heading.current?.focus();},[]);
 useEffect(()=>{
  const controller=new AbortController();setResult(null);setError(false);
  if(ids.length<2||ids.length>3){setLoading(false);return()=>controller.abort();}
  setLoading(true);
  api<{items:Item[]}>('/saved-places/summary',{method:'POST',body:JSON.stringify({place_ids:ids,versions_per_place:1}),signal:controller.signal})
   .then(payload=>{if(!controller.signal.aborted){const accepted=comparisonItems(payload,ids) as Item[];setResult({key,items:accepted});setLoading(false);}})
   .catch(()=>{if(!controller.signal.aborted){setError(true);setLoading(false);}});
  return()=>controller.abort();
 },[key,refresh]);
 const mixed=new Set(items.flatMap(item=>item.place?[item.place.kind]:[])).size>1;
 return <section className="place-comparison" aria-labelledby="place-comparison-title" aria-busy={loading}>
   <div className="place-comparison-heading"><h2 id="place-comparison-title" tabIndex={-1} ref={heading}>{words.title}</h2><button onClick={onClose}>{words.close}</button></div>
   <p className="callout">{words.intro}</p><p className="muted">{words.dates}</p>
   <div role="status">{loading?t('loading'):error?words.failure:ids.length<2?words.empty:null}</div>
   {error&&<button onClick={()=>setRefresh(v=>v+1)}>{words.retry}</button>}
   {mixed&&<p className="comparison-notice">{words.mixed}</p>}
   <div className="place-comparison-grid">{items.map(item=>{
    const place=item.place;
    if(!place)return <article className="comparison-place" key={item.id}><h3>{item.id}</h3><p>{words.missing}</p></article>;
    const url=safeReference(place.source.url);
    return <article className="comparison-place" key={item.id}>
     <span className="eyebrow">{words[place.kind]} · {place.state}</span><h3>{place.name}</h3>
     {item.status==='outside_current_profile'&&<p className="comparison-notice">{words.outside}</p>}
     <dl><div><dt>{words.address}</dt><dd>{place.address||words.noAddress}</dd></div>
      <div><dt>{words.phone}</dt><dd>{place.phone||words.noPhone}</dd></div>
      <div><dt>{words.services}</dt><dd>{place.declared_services.length?<ul>{place.declared_services.map(value=><li key={value}>{t(value)}</li>)}</ul>:words.noServices}</dd></div>
      <div><dt>{words.municipality}</dt><dd>{place.municipality_id} · {place.state}</dd></div>
      <div><dt>{words.reference}</dt><dd>{formatReferenceDate(place.source.reference_date,locale)}</dd></div>
      <div><dt>{words.collected}</dt><dd>{watchDate(place.source.collected_at,locale,t)}</dd></div></dl>
     <p className="comparison-source"><strong>{formatDataset(place.source.dataset,locale)}</strong><br/><code>{place.source.record_id}</code><br/>{url&&<a href={url} target="_blank" rel="noopener noreferrer">{words.source} ↗</a>}</p>
     <button onClick={()=>onSelect(item.id)}>{words.details}</button>
    </article>;
   })}</div>
   {items.length>0&&<button onClick={()=>setRefresh(v=>v+1)} disabled={loading}>{words.refresh}</button>}
 </section>;
}
