import {useId,useLayoutEffect,useMemo,useState} from 'react';
import {createLatestTask} from './latest-task.mjs';
import type {Locale} from './types';
import {resourceShareURL} from './resource-route.mjs';
type T=(key:string)=>string;
type Criteria={q?:string;profile?:string;state?:string;municipality?:string;id?:string;locale?:string};
export function ShareResource({criteria,t,label}:{criteria:Criteria;t:T;label:string}) {
  const [open,setOpen]=useState(false);
  const [state,setState]=useState({link:'',busy:false,message:''});
  const inputId=useId();
  const link=resourceShareURL(window.location.href,criteria);
  const task=useMemo(()=>createLatestTask(),[link,open]);
  const current=state.link===link?state:{link,busy:false,message:''};
  useLayoutEffect(()=>{
    setState({link,busy:false,message:''});
    return()=>task.cancel();
  },[task,link]);
  async function copy(){
    setState({link,busy:true,message:''});
    await task.run(async()=>navigator.clipboard.writeText(link),{
      success:()=>setState({link,busy:false,message:'resourceCopied'}),
      failure:()=>setState({link,busy:false,message:'resourceCopyFallback'})
    });
  }
  return <div className="resource-share"><button aria-expanded={open} onClick={()=>{task.cancel();setOpen(value=>!value);setState({link,busy:false,message:''});}}>{t(label)}</button>
    {open&&<div className="share-panel"><p>{t('resourceShareHint')}</p><label htmlFor={inputId}>{t('resourceLink')}</label>
      <input id={inputId} readOnly value={link} onFocus={event=>event.currentTarget.select()}/>
      <button disabled={current.busy} onClick={copy}>{t('resourceCopy')}</button>{current.message&&<p role="status">{t(current.message)}</p>}</div>}
  </div>;
}
export function ResourceDownloads({id,locale,t,revision}:{id:string;locale:Locale;t:T;revision?:number}) {
  return <details className="resource-downloads"><summary>{t('resourceDownload')}{revision?' · '+revision:''}</summary>
    <p>{t('resourceExportNotice')}</p><div className="download-links">{(['text','csv','json'] as const).map(format=>{
      const params=new URLSearchParams({format,locale});if(revision)params.set('revision',String(revision));
      return <a key={format} download href={'/api/resource-export/'+encodeURIComponent(id)+'?'+params}>{format==='text'?t('resourceDownloadText'):format.toUpperCase()}</a>;
    })}</div></details>;
}
