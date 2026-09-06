import {useEffect,useState} from 'react';
import {api} from './api';
import {selectionExportURL,statusText} from './resource-status.mjs';
import type {Locale} from './types';
import './resource-status.css';

type T=(key:string)=>string;
type Attempt={status:string;started_at:string|null;finished_at:string|null};
type Coverage={profiles:{profile:string;loaded_records:number;last_attempt:Attempt|null;last_successful_import_at:string|null}[]};
export function ResourceCoverage({t,locale}:{t:T;locale:Locale}){
  const [data,setData]=useState<Coverage|null>(null),[failed,setFailed]=useState(false),[attempt,setAttempt]=useState(0);
  const text=(key:string)=>statusText(locale,key);
  useEffect(()=>{const controller=new AbortController();setData(null);setFailed(false);
    api<Coverage>('/resource-coverage',{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setData(value);})
      .catch(()=>{if(!controller.signal.aborted)setFailed(true);});return()=>controller.abort();
  },[attempt]);
  return <section className="resource-status" aria-label={text('title')}><details><summary>{text('title')}</summary>
    <p>{text('notice')}</p>{failed?<div role="status"><p>{text('failure')}</p><button onClick={()=>setAttempt(value=>value+1)}>{text('retry')}</button></div>
      :!data?<p role="status">{text('loading')}</p>:<div className="resource-status-grid">{data.profiles.map(row=><article key={row.profile}>
        <h3>{t(row.profile)}</h3><p><strong>{row.loaded_records.toLocaleString(locale)}</strong> {text('loaded')}</p>
        <p className={row.last_attempt?.status==='failed'?'import-failed':''}>{text(row.last_attempt?.status||'none')}</p>
        {row.last_attempt?.status==='failed'&&row.loaded_records>0&&<p>{text('kept')}</p>}
        {row.last_successful_import_at&&<p>{text('date')}: <time dateTime={row.last_successful_import_at}>{new Date(row.last_successful_import_at).toLocaleString(locale)}</time></p>}
      </article>)}</div>}</details></section>;
}

export function CollectionDownloads({criteria,locale}:{criteria:Record<string,string|undefined>;locale:Locale}){
  const [busy,setBusy]=useState(false),[status,setStatus]=useState('');const text=(key:string)=>statusText(locale,key);
  const selectionKey=JSON.stringify(criteria);
  useEffect(()=>setStatus(''),[selectionKey,locale]);
  async function download(format:'json'|'text'|'csv'){
    setBusy(true);setStatus('');
    try{const response=await fetch(selectionExportURL(criteria,format,locale),{credentials:'omit'});
      if(!response.ok)throw new Error('export_failed');
      const blob=await response.blob(),url=URL.createObjectURL(blob),anchor=document.createElement('a');
      anchor.href=url;anchor.download='brasildetodos-resource-selection.'+(format==='text'?'txt':format);
      document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);setStatus('ready');
    }catch{setStatus('exportFailed');}finally{setBusy(false);}
  }
  return <div className="collection-downloads"><details><summary>{text('exportTitle')}</summary><p>{text('exportNotice')}</p>
    <div>{(['text','csv','json'] as const).map(format=><button key={format} disabled={busy} onClick={()=>download(format)}>{text(format)}</button>)}</div>
    {status&&<p role="status">{text(status)}</p>}</details></div>;
}
