// SPDX-License-Identifier: AGPL-3.0-or-later
import {useId,useState} from 'react';
import {safeReference} from './i18n.mjs';
import {resourceAmountText} from './resource-i18n.mjs';
import {historyFields} from './resource-history.mjs';
import {compareResourceVersions,comparisonText} from './resource-comparison.mjs';
import type {PublicResource} from './Resources';
import type {Locale} from './types';
import './resource-comparison.css';

type Version={revision:number;resource:PublicResource};
export default function ResourceComparison({older,newer,locale}:{older:Version;newer:Version;locale:Locale}){
 const [open,setOpen]=useState(false),id=useId();
 const result=compareResourceVersions(older,newer),text=(key:string)=>comparisonText(locale,key);
 return <div className="resource-comparison">
  <button aria-expanded={open} aria-controls={id} onClick={()=>setOpen(value=>!value)}>{text(open?'close':'open')}</button>
  {open&&<section id={id} aria-label={text('open')}>
   <p className="comparison-notice">{text('notice')}</p>
   {result.status!=='comparable'?<p role="status">{text('unavailable')}</p>:<>
    <div className="comparison-origins">{[[older,'before'],[newer,'after']].map(([raw,label])=>{
     const version=raw as Version,source=version.resource.source,url=safeReference(source.url);
     return <div key={label as string}><h4>{text(label as string)} · {version.revision}</h4>
      <p>{text('source')}: {source.dataset} · {source.reference_date||text('unknown')}</p>
      {url&&<a href={url} target="_blank" rel="noopener noreferrer">{text('source')} ↗</a>}
     </div>;
    })}</div>
    {result.changes.length===0?<p>{text('none')}</p>:<div className="comparison-fields">{result.changes.map((field:{key:string;kind:string;before:unknown;after:unknown})=>
     <article key={field.key} className="comparison-field"><h4>{historyFields([field.key],locale)[0].label}</h4>
      <dl>{(['before','after'] as const).map(side=><div key={side}><dt>{text(side)}</dt><dd>{field[side]===null?text('unknown'):
       field.kind==='amount'?resourceAmountText(field[side],locale):String(field[side])}</dd></div>)}</dl>
     </article>)}</div>}
   </>}
  </section>}
 </div>;
}
