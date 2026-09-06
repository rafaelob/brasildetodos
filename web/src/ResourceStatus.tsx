import {useEffect,useLayoutEffect,useMemo,useState} from 'react';
import {createLatestTask} from './latest-task.mjs';
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
  const scope=JSON.stringify([criteria,locale]);
  const task=useMemo(()=>createLatestTask(),[scope]);
  const [state,setState]=useState({scope:'',busy:false,status:''});
  const text=(key:string)=>statusText(locale,key);
  const current=state.scope===scope?state:{scope,busy:false,status:''};
  // Invalidate the old selection at commit, before asynchronous responses publish.
  useLayoutEffect(()=>{
    setState({scope,busy:false,status:''});
    return()=>task.cancel();
  },[task,scope]);
  async function download(format:'json'|'text'|'csv'){
    setState({scope,busy:true,status:'preparing'});
    await task.run(async signal=>{
      const response=await fetch(selectionExportURL(criteria,format,locale),{credentials:'omit',signal});
      if(!response.ok)throw new Error('export_failed');
      return response.blob();
    },{
      success:blob=>{
        const url=URL.createObjectURL(blob),anchor=document.createElement('a');
        try{
          anchor.href=url;anchor.download='brasildetodos-resource-selection.'+(format==='text'?'txt':format);
          document.body.append(anchor);anchor.click();
        }finally{anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
        setState({scope,busy:false,status:'ready'});
      },
      failure:()=>setState({scope,busy:false,status:'exportFailed'})
    });
  }
  function cancel(){task.cancel();setState({scope,busy:false,status:'cancelled'});}
  return <div className="collection-downloads"><details><summary>{text('exportTitle')}</summary><p>{text('exportNotice')}</p>
    <div>{(['text','csv','json'] as const).map(format=><button key={format} disabled={current.busy} onClick={()=>download(format)}>{text(format)}</button>)}</div>
    {current.busy&&<button onClick={cancel}>{text('cancel')}</button>}
    {current.status&&<p role="status" aria-live="polite">{text(current.status)}</p>}</details></div>;
}
