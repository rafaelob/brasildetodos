import {useEffect,useState} from 'react';
import type {FormEvent} from 'react';
import {api,downloadJSON} from './api';
import {safeReference,formatDataset,formatReferenceDate} from './i18n.mjs';
import type {Locale,Observation,Source} from './types';

type Translator=(key:string)=>string;
type Resource={id:string;kind:string;title:string;municipality_id:string|null;source:Source;attributes:Record<string,unknown>};
type DocumentMeta={id:string;title:string;state:string;source:Source;pages:number};
type Relationship={id:string;place_id:string;resource_id:string;document_id:string;page:number;excerpt:string;justification?:string;status:string;revision:number;can_review?:boolean;resource?:Resource;document?:{title:string;source:Source}};

function SourceLink({source,t,locale='pt-BR'}:{source:Source;t:Translator;locale?:Locale}){
  const url=safeReference(source.url);
  return <div className="source"><strong>{formatDataset(source.dataset,locale)}</strong><p>{t('reference')}: {formatReferenceDate(source.reference_date,locale)}</p>{url&&<a href={url} target="_blank" rel="noopener noreferrer">{t('sourceOriginal')} ↗</a>}<details><summary>SHA-256</summary><code>{source.snapshot_sha256}</code></details></div>;
}

export function PlaceEvidence({placeId,t,locale='pt-BR'}:{placeId:string;t:Translator;locale?:Locale}){
  const [rows,setRows]=useState<Relationship[]|null>(null),[error,setError]=useState(false);
  useEffect(()=>{const controller=new AbortController();setRows(null);setError(false);api<Relationship[]>('/place-links/'+encodeURIComponent(placeId),{signal:controller.signal}).then(setRows).catch(()=>{if(!controller.signal.aborted)setError(true);});return()=>controller.abort();},[placeId]);
  return <section aria-label={t('links')}><h2>{t('links')}</h2><p className="callout">{t('linkNotice')}</p>{error?<p role="status">{t('failure')}</p>:rows===null?<p>{t('loading')}</p>:rows.length===0?<p>{t('linksEmpty')}</p>:rows.map(row=><article className="panel" key={row.id}><span className="pill">{t('reviewed')}</span><h3>{row.resource?.title}</h3><p>{row.document?.title} · {t('pageNumber')} {row.page}</p><blockquote>{row.excerpt}</blockquote>{row.document&&<SourceLink source={row.document.source} t={t} locale={locale}/>}</article>)}</section>;
}

export function RegionResources({municipalityId,t,locale='pt-BR'}:{municipalityId:string;t:Translator;locale?:Locale}){
  const [rows,setRows]=useState<Resource[]>([]),[total,setTotal]=useState(0),[page,setPage]=useState(1),[error,setError]=useState(false);
  useEffect(()=>{setPage(1);},[municipalityId]);
  useEffect(()=>{const controller=new AbortController();setError(false);api<{items:Resource[];total:number}>('/resources?municipality_id='+encodeURIComponent(municipalityId)+'&page='+page,{signal:controller.signal}).then(result=>{setRows(result.items);setTotal(result.total);}).catch(()=>{if(!controller.signal.aborted)setError(true);});return()=>controller.abort();},[municipalityId,page]);
  return <section><h2>{t('resourcesTitle')}</h2><p>{t('resourceScope')}</p>{error&&<p role="status">{t('failure')}</p>}{rows.map(row=><article className="panel" key={row.id}><h3>{row.title}</h3><code>{row.id}</code><SourceLink source={row.source} t={t} locale={locale}/></article>)}{!rows.length&&!error&&<p>{t('empty')}</p>}{total>30&&<div className="pager"><button disabled={page===1} onClick={()=>setPage(value=>value-1)}>{t('prev')}</button><span>{page}</span><button disabled={page*30>=total} onClick={()=>setPage(value=>value+1)}>{t('next')}</button></div>}</section>;
}

function SourceFields({t}:{t:Translator}){
  return <fieldset className="source-fields"><legend>{t('source')}</legend><label>{t('sourceDataset')}<input name="dataset" required maxLength={80}/></label><label>{t('sourceRecord')}<input name="record_id" required maxLength={200}/></label><label>{t('sourceURL')}<input name="url" type="url" required maxLength={2000}/></label><label>{t('sourceHash')}<input name="snapshot_sha256" required pattern="[a-f0-9]{64}" maxLength={64}/></label><label>{t('referenceDate')}<input name="reference_date" maxLength={40}/></label><label>{t('collectedAt')}<input name="collected_at" type="datetime-local" required/></label></fieldset>;
}
function sourceFrom(form:FormData){return {dataset:String(form.get('dataset')||''),record_id:String(form.get('record_id')||''),url:String(form.get('url')||''),snapshot_sha256:String(form.get('snapshot_sha256')||''),reference_date:form.get('reference_date')||null,collected_at:new Date(String(form.get('collected_at'))).toISOString()};}

type Candidate={field:string;raw:string;value:unknown};

function fieldLabel(field:string,t:Translator):string{
  switch(field){
    case 'agreement_reference':return t('fieldAgreement');
    case 'proposal_reference':return t('fieldProposal');
    case 'contract_reference':return t('fieldContract');
    case 'amendment_reference':return t('fieldAmendment');
    case 'process_reference':return t('fieldProcess');
    case 'cnpj_reference':return t('fieldCnpj');
    case 'estimated_cents':return t('fieldEstimated');
    case 'global_value':return t('fieldGlobal');
    case 'planned_capacity':return t('fieldCapacity');
    case 'legal_basis':return t('fieldLegalBasis');
    default:return field;
  }
}

export default function Workbench({t,locale='pt-BR'}:{t:Translator;locale?:Locale}){
  const [documents,setDocuments]=useState<DocumentMeta[]>([]),[queue,setQueue]=useState<Relationship[]>([]),[resources,setResources]=useState<Resource[]>([]);
  const [docId,setDocId]=useState(''),[page,setPage]=useState(1),[pageText,setPageText]=useState<string|null>(null),[status,setStatus]=useState('candidate');
  const [candidatesList,setCandidatesList]=useState<Candidate[]>([]),[pageRoute,setPageRoute]=useState<string>(''),[excerptInput,setExcerptInput]=useState<string>('');
  const [message,setMessage]=useState(''),[busy,setBusy]=useState(false);
  async function load(){const[d,l,r]=await Promise.all([api<DocumentMeta[]>('/workbench/documents'),api<Relationship[]>('/workbench/links?status='+status),api<{items:Resource[]}>('/resources?limit=100')]);setDocuments(d);setQueue(l);setResources(r.items);}
  useEffect(()=>{let active=true;Promise.all([api<DocumentMeta[]>('/workbench/documents'),api<Relationship[]>('/workbench/links?status='+status),api<{items:Resource[]}>('/resources?limit=100')]).then(([d,l,r])=>{if(active){setDocuments(d);setQueue(l);setResources(r.items);}}).catch(()=>{if(active)setMessage('failure');});return()=>{active=false;};},[status]);
  async function execute(action:()=>Promise<void>){setBusy(true);setMessage('');try{await action();setMessage('added');await load();}catch{setMessage('failure');}finally{setBusy(false);}}
  function register(event:FormEvent<HTMLFormElement>,kind:'documents'|'resources'){
    event.preventDefault();const form=event.currentTarget,values=new FormData(form);
    execute(async()=>{const common={title:String(values.get('title')),source:sourceFrom(values)};
      const body=kind==='documents'?common:{...common,id:String(values.get('id')),kind:String(values.get('kind')),municipality_id:values.get('municipality_id')||null};
      const result=await api<{id:string}>('/workbench/'+kind,{method:'POST',body:JSON.stringify(body)});
      if(kind==='documents'){setDocId(result.id);setPageText(null);setCandidatesList([]);setPageRoute('');}form.reset();});
  }
  async function openPage(){setBusy(true);setMessage('');setPageText(null);setCandidatesList([]);setPageRoute('');try{const result=await api<{page:{text:string;ocr_candidate_text?:string;route?:string;candidates?:Candidate[];ocr_candidates?:Candidate[]}}>('/workbench/documents/'+encodeURIComponent(docId)+'/pages/'+page);setPageText([result.page.text,result.page.ocr_candidate_text].filter(Boolean).join('\n\n'));setPageRoute(result.page.route||'native');setCandidatesList([...(result.page.candidates||[]),...(result.page.ocr_candidates||[])]);}catch{setMessage('missingExtraction');}finally{setBusy(false);}}
  function propose(event:FormEvent<HTMLFormElement>){event.preventDefault();const form=event.currentTarget,values=new FormData(form);execute(async()=>{await api('/workbench/links',{method:'POST',body:JSON.stringify({place_id:values.get('place_id'),resource_id:values.get('resource_id'),document_id:docId,page,excerpt:excerptInput||values.get('excerpt'),justification:values.get('justification')})});form.reset();setExcerptInput('');});}
  function review(event:FormEvent<HTMLFormElement>,row:Relationship){event.preventDefault();const values=new FormData(event.currentTarget);execute(async()=>{await api('/workbench/links/'+row.id+'/review',{method:'POST',body:JSON.stringify({decision:values.get('decision'),note:values.get('note'),expected_revision:row.revision,public_excerpt_checked:values.get('checked')==='on'})});});}
  return <section className="page"><h1>{t('workbench')}</h1><p className="callout">{t('extractionOperator')}</p><p>{t('independentReview')}</p>{message&&<p role="status">{t(message)}</p>}
    <div className="detail-columns"><div>
      <details className="panel"><summary>{t('registerResource')}</summary><form onSubmit={event=>register(event,'resources')}><label>{t('resourceID')}<input name="id" required pattern="[a-z0-9_-]+:[A-Za-z0-9._/\-]+" maxLength={200}/></label><label>{t('title')}<input name="title" required minLength={5} maxLength={300}/></label><label htmlFor="resource-kind">{t('resourceKind')}</label><select id="resource-kind" name="kind">{['contract','instrument','proposal','work'].map(kind=><option value={kind} key={kind}>{t('resource'+kind[0].toUpperCase()+kind.slice(1))}</option>)}</select><label>{t('municipalityID')}<input name="municipality_id" pattern="[0-9]{7}" maxLength={7}/></label><SourceFields t={t}/><button disabled={busy} className="primary">{t('registerResource')}</button></form></details>
      <details className="panel"><summary>{t('registerDocument')}</summary><form onSubmit={event=>register(event,'documents')}><label>{t('documentTitle')}<input name="title" required minLength={5} maxLength={300}/></label><SourceFields t={t}/><button disabled={busy} className="primary">{t('registerDocument')}</button></form></details>
      <article className="panel"><div className="workbench-panel-header"><h2>{t('sourceRestricted')}</h2>{pageRoute&&<span className={'route-badge route-'+pageRoute}>{pageRoute==='ocr_candidate'?t('routeOcrCandidate'):pageRoute==='review_encoding'?t('routeReviewEncoding'):pageText&&pageText.includes('ocr_candidate_text')?t('routeOcrProcessed'):t('routeNative')}</span>}</div><label htmlFor="selected-document">{t('selectedDocument')}</label><select id="selected-document" value={docId} onChange={event=>{setDocId(event.target.value);setPage(1);setPageText(null);setCandidatesList([]);setPageRoute('');}}><option value="">{t('selectedDocument')}</option>{documents.map(doc=><option key={doc.id} value={doc.id}>{doc.title} · {doc.pages}</option>)}</select><label>{t('pageNumber')}<input type="number" min={1} max={1000} value={page} onChange={event=>{setPage(Number(event.target.value));setPageText(null);setCandidatesList([]);setPageRoute('');}}/></label><button disabled={!docId||busy||page<1} onClick={openPage}>{t('loadPage')}</button>{candidatesList.length>0&&<div className="candidates-container"><h3>{t('extractedCandidates')}</h3><div className="candidates-list">{candidatesList.map((c,i)=><div key={i} className="candidate-card"><span className="candidate-badge">{fieldLabel(c.field,t)}</span><strong className="candidate-text">{c.raw||String(c.value)}</strong><button type="button" className="candidate-apply-btn" onClick={()=>setExcerptInput(c.raw||String(c.value))} title={t('useAsExcerpt')}>↳ {t('useAsExcerpt')}</button></div>)}</div></div>}{pageText!==null&&<pre className="extracted-text" aria-label={t('sourceRestricted')}>{pageText}</pre>}</article>
    </div><div><form className="panel" onSubmit={propose}><h2>{t('proposeLink')}</h2><label>{t('placeIdentifier')}<input name="place_id" required maxLength={180}/></label><label htmlFor="link-resource">{t('resourceID')}</label><input id="link-resource" name="resource_id" list="known-resources" required maxLength={200}/><datalist id="known-resources">{resources.map(resource=><option key={resource.id} value={resource.id}>{resource.title}</option>)}</datalist><label>{t('excerpt')}<textarea name="excerpt" value={excerptInput} onChange={e=>setExcerptInput(e.target.value)} required minLength={10} maxLength={1500}/></label><label>{t('justification')}<textarea name="justification" required minLength={20} maxLength={2000}/></label><p>{t('selectedDocument')}: <code>{docId||t('unknown')}</code> · {t('pageNumber')} {page}</p><button className="primary" disabled={busy||!docId||pageText===null}>{t('proposeLink')}</button></form></div></div>
    <h2>{t('reviewAction')}</h2><label htmlFor="review-status">{t('reviewAction')}</label><select id="review-status" value={status} onChange={event=>setStatus(event.target.value)}>{['candidate','reviewed','rejected','retracted'].map(value=><option key={value} value={value}>{t(value)}</option>)}</select><button onClick={()=>execute(async()=>{})} disabled={busy}>{t('refresh')}</button>
    {queue.map(row=><article className="panel" key={row.id}><p><code>{row.place_id}</code> → <code>{row.resource_id}</code></p><blockquote>{row.excerpt}</blockquote><p>{row.justification}</p><p>{t('pageNumber')}: {row.page}</p>{row.can_review&&['candidate','reviewed'].includes(row.status)?<form onSubmit={event=>review(event,row)}><label htmlFor={'review-decision-'+row.id}>{t('reviewAction')}</label><select id={'review-decision-'+row.id} name="decision">{row.status==='reviewed'?<option value="retracted">{t('retracted')}</option>:<><option value="reviewed">{t('reviewed')}</option><option value="rejected">{t('rejected')}</option></>}</select><label>{t('reviewNote')}<textarea name="note" required minLength={20} maxLength={2000}/></label>{row.status==='candidate'&&<label className="check"><input type="checkbox" name="checked"/>{t('publicExcerptCheck')}</label>}<button disabled={busy} className="primary">{t('submit')}</button></form>:<p>{t('independentReview')}</p>}</article>)}
  </section>;
}

export function PrivacyControls({rows,t,onChange,onDeleted}:{rows:Observation[];t:Translator;onChange:()=>void;onDeleted:()=>void}){
  const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
  async function act(action:()=>Promise<void>){setBusy(true);setMessage('');try{await action();setMessage('added');}catch{setMessage('failure');}finally{setBusy(false);}}
  function remove(event:FormEvent<HTMLFormElement>){event.preventDefault();const form=event.currentTarget,values=new FormData(form);act(async()=>{await api('/account/delete',{method:'POST',body:JSON.stringify({password:values.get('password'),confirmed:values.get('confirmed')==='on'})});form.reset();onDeleted();});}
  return <section className="panel"><h2>{t('privacyTitle')}</h2>{message&&<p role="status">{t(message)}</p>}<button disabled={busy} onClick={()=>act(async()=>downloadJSON('brasildetodos-my-data.json',await api('/account/export')))}>{t('exportAccount')}</button>
    {rows.filter(row=>!['withdrawn','retracted'].includes(row.status)).map(row=><div className="withdraw-control" key={row.id}><p>{row.observation.body}</p><button disabled={busy} onClick={()=>act(async()=>{await api('/observations/'+row.id+'/withdraw',{method:'POST'});onChange();})}>{t('withdrawContribution')}</button></div>)}
    <details><summary>{t('deactivateAccount')}</summary><p>{t('deactivationNote')}</p><form onSubmit={remove}><label>{t('deletePassword')}<input type="password" name="password" autoComplete="current-password" minLength={12} maxLength={128} required/></label><label className="check"><input type="checkbox" name="confirmed" required/>{t('deactivationConfirm')}</label><button disabled={busy}>{t('deleteButton')}</button></form></details>
  </section>;
}
