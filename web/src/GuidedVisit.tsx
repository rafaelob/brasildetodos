import {useEffect,useId,useRef,useState} from 'react';
import {api,downloadJSON} from './api';
import {safeReference} from './i18n.mjs';
import {visitText} from './visit-text.mjs';
import {composeVisit,publicObservationReport,visitGuide} from './visit-guide.mjs';
import type {Locale,Observation,Place} from './types';
import './visit.css';

export function ObservationDownloads({row,locale}:{row:Observation;locale:Locale}) {
  if(row.status!=='approved')return null;
  const words=visitText[locale];
  return <details className="visit-downloads"><summary>{words.export}</summary><p>{words.publicNotice}</p>
    <button onClick={()=>downloadJSON('brasildetodos-observation-'+row.id+'.json',publicObservationReport(row,locale))}>JSON</button></details>;
}

/** Drafting aid on the existing moderated API; no new server route or permission. */
export default function GuidedVisit({place,locale}:{place:Place;locale:Locale}) {
  const words=visitText[locale],uid=useId(),mounted=useRef(false),epoch=useRef(0);
  const [open,setOpen]=useState(false),[answers,setAnswers]=useState<Record<string,string>>({});
  const [date,setDate]=useState(''),[note,setNote]=useState(''),[consent,setConsent]=useState(false);
  const [phase,setPhase]=useState<'ready'|'sending'|'saved'>('ready');
  const [error,setError]=useState(false);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;epoch.current++;};},[]);
  const guide=visitGuide(place.kind,locale);
  let preview='',budget=false;
  try{preview=composeVisit(place,locale,answers,note);}catch(reason){budget=reason instanceof Error&&reason.message==='observation_budget';}
  async function submit(event:React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if(phase!=='ready'||!consent||!preview)return;
    const ticket=++epoch.current;setPhase('sending');setError(false);
    try {
      await api('/observations',{method:'POST',body:JSON.stringify({place_id:place.id,mode:'field',observed_on:date,body:preview,reference_url:place.source.url,consent:true})});
      if(mounted.current&&ticket===epoch.current){setPhase('saved');setNote('');setAnswers({});setConsent(false);}
    }catch{if(mounted.current&&ticket===epoch.current){setPhase('ready');setError(true);}}
  }
  if(!place.catalogue_eligible)return null;
  return <section className="guided-visit" aria-label={words.open}>
    {!open?<button className="primary" onClick={()=>setOpen(true)}>{words.open}</button>:<>
      <div className="visit-heading"><h3>{words.open}</h3><button type="button" disabled={phase==='sending'} onClick={()=>setOpen(false)}>{words.close}</button></div>
      <p>{words.intro}</p><p className="muted">{words.privateNotice}</p>
      {phase==='saved'?<div role="status"><p>{words.saved}</p><button onClick={()=>{setPhase('ready');setDate('');}}>{words.again}</button></div>:<form onSubmit={submit} aria-busy={phase==='sending'}>
        <p className="callout">{words.authored} {words.methodNote}</p>
        <p>{place.name}</p><p className="muted">{words.source}: {place.source.dataset} · {place.source.reference_date||words.missing}{safeReference(place.source.url)&&<> · <a href={safeReference(place.source.url)!} target="_blank" rel="noopener noreferrer">{words.source} ↗</a></>}</p>
        <fieldset className="visit-fields" disabled={phase==='sending'}><legend>{words.summary}</legend>
          {guide.items.map((item:{id:string;label:string;allowed_answers:string[]},index:number)=><fieldset className="visit-question" key={item.id}>
            <legend><span aria-hidden="true">{index+1}. </span>{item.label}</legend>
            <div className="visit-answers">{item.allowed_answers.map((answer:string)=><label key={answer}><input type="radio" name={uid+item.id} value={answer} required checked={answers[item.id]===answer} onChange={()=>setAnswers(old=>({...old,[item.id]:answer}))}/>{words[answer as 'yes'|'no'|'unknown']}</label>)}</div>
          </fieldset>)}
          <label htmlFor={uid+'date'}>{words.date}</label><input id={uid+'date'} type="date" max={new Date().toISOString().slice(0,10)} required value={date} onChange={e=>setDate(e.target.value)}/>
          <label htmlFor={uid+'note'}>{words.note}</label><textarea id={uid+'note'} minLength={20} maxLength={500} required rows={4} value={note} onChange={e=>setNote(e.target.value)} aria-describedby={uid+'help'}/>
          <p className="muted" id={uid+'help'}>{words.help}</p>
          <label className="check"><input type="checkbox" required checked={consent} onChange={e=>setConsent(e.target.checked)}/>{words.consent}</label>
        </fieldset>
        {budget&&<p role="alert">{words.budget}</p>}
        {preview&&<details className="visit-preview"><summary>{words.preview}</summary><pre>{preview}</pre><small>{Array.from(preview).length} / 1200</small></details>}
        {error&&<p role="alert">{words.sendError}</p>}
        <button className="primary" disabled={phase==='sending'||budget} type="submit">{phase==='sending'?words.sending:words.submit}</button>
        <p className="muted">{words.authored} · <code>{guide.id}</code></p>
      </form>}
    </>}
  </section>;
}
