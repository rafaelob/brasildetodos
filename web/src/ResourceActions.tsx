import {useId,useState} from 'react';
import type {Locale} from './types';
import {resourceShareURL} from './resource-route.mjs';
type T=(key:string)=>string;
type Criteria={q?:string;profile?:string;state?:string;municipality?:string;id?:string;locale?:string};
export function ShareResource({criteria,t,label}:{criteria:Criteria;t:T;label:string}) {
  const [open,setOpen]=useState(false),[message,setMessage]=useState('');
  const inputId=useId();
  const link=resourceShareURL(window.location.href,criteria);
  async function copy(){
    try{await navigator.clipboard.writeText(link);setMessage('resourceCopied');}
    catch{setMessage('resourceCopyFallback');}
  }
  return <div className="resource-share"><button aria-expanded={open} onClick={()=>{setOpen(value=>!value);setMessage('');}}>{t(label)}</button>
    {open&&<div className="share-panel"><p>{t('resourceShareHint')}</p><label htmlFor={inputId}>{t('resourceLink')}</label>
      <input id={inputId} readOnly value={link} onFocus={event=>event.currentTarget.select()}/>
      <button onClick={copy}>{t('resourceCopy')}</button>{message&&<p role="status">{t(message)}</p>}</div>}
  </div>;
}
export function ResourceDownloads({id,locale,t,revision}:{id:string;locale:Locale;t:T;revision?:number}) {
  return <details className="resource-downloads"><summary>{t('resourceDownload')}{revision?' · '+revision:''}</summary>
    <p>{t('resourceExportNotice')}</p><div className="download-links">{(['text','csv','json'] as const).map(format=>{
      const params=new URLSearchParams({format,locale});if(revision)params.set('revision',String(revision));
      return <a key={format} download href={'/api/resource-export/'+encodeURIComponent(id)+'?'+params}>{format==='text'?t('resourceDownloadText'):format.toUpperCase()}</a>;
    })}</div></details>;
}
