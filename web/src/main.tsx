import {createLatestTask} from './latest-task.mjs';
import {StrictMode,useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {api,downloadJSON} from './api';
import {money,safeReference,formatDataset,formatReferenceDate} from './i18n.mjs';
import {uiText} from './ui-text.mjs';
import MapView from './Map';
import Resources from './Resources';
import Region from './Region';
import Groups from './Groups';
import SavedPlaces from './SavedPlaces';
import CatalogCoverage from './CatalogCoverage';
import GuidedVisit,{ObservationDownloads} from './GuidedVisit';
import {favoriteIds} from './watch-state.mjs';
import {parseResourceRoute} from './resource-route.mjs';
import Workbench,{PlaceEvidence,PrivacyControls} from './Workbench';
import {CivicLogo} from './CivicLogo';
import type {Detail,Locale,Money,Observation,Place,Source,User} from './types';
import './style.css';
import './detail-status.css';
import './workbench.css';

type Town={id:string;name:string;state:string};
type History={at:string;type:string;fields:string[];before:Place|null;after:Place};
type Config={registration_enabled:boolean;source_code:string;revision:string};
const states='AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' ');
const ref=(id:string)=>encodeURIComponent(id);
const getStored=(key:string,fallback:unknown)=>{try{return JSON.parse(localStorage.getItem(key)||'null')??fallback;}catch{return fallback;}};

function App(){
  const [locale,setLocale]=useState<Locale>(()=>{const value=parseResourceRoute(window.location.hash)?.locale||getStored('bdt:locale','pt-BR');return ['pt-BR','en','es'].includes(value)?value:'pt-BR';});
  const t=(key:string)=>uiText(locale,key);
  const [resourceRoute,setResourceRoute]=useState(window.location.hash);
  const [view,setView]=useState(()=>parseResourceRoute(window.location.hash)?'resources':'explore'),[query,setQuery]=useState(''),[kind,setKind]=useState(''),[state,setState]=useState(''),[town,setTown]=useState(''),[bbox,setBbox]=useState('');
  const [towns,setTowns]=useState<Town[]>([]),[places,setPlaces]=useState<Place[]>([]),[page,setPage]=useState(1),[total,setTotal]=useState(0);
  const [focusCoords,setFocusCoords]=useState<[number,number]|null>(null);
  const [busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[detail,setDetail]=useState<Detail|null>(null),[history,setHistory]=useState<History[]>([]);
  const [user,setUser]=useState<User|null>(null),[config,setConfig]=useState<Config|null>(null);
  const [favorites,setFavorites]=useState<string[]>(()=>{const value=getStored('bdt:favorites',[]);return favoriteIds(value);});
  const [mine,setMine]=useState<Observation[]>([]),[queue,setQueue]=useState<Observation[]>([]);
  const [regionId,setRegionId]=useState('');
  const [tab,setTab]=useState('service');
  const searchVersion=useRef(0),detailTask=useRef(createLatestTask());
  const [detailBusy,setDetailBusy]=useState(false);
  function cancelDetails(){detailTask.current.cancel();setDetailBusy(false);}
  useEffect(()=>()=>detailTask.current.cancel(),[]);
  function failure(){setNotice('failure');}
  useEffect(()=>{const changed=()=>{const hash=window.location.hash,route=parseResourceRoute(hash);
    if(route){setResourceRoute(hash);setView('resources');setDetail(null);setLocale(route.locale as Locale);cancelDetails();}
  };window.addEventListener('hashchange',changed);return()=>window.removeEventListener('hashchange',changed);},[]);
  useEffect(()=>{document.documentElement.lang=locale;try{localStorage.setItem('bdt:locale',JSON.stringify(locale));}catch{}},[locale]);
  useEffect(()=>{api<Config>('/config').then(setConfig).catch(failure);api<User>('/auth/me').then(setUser).catch(()=>{});},[]);
  useEffect(()=>{let active=true;api<Town[]>('/municipalities'+(state?'?state='+state:'')).then(value=>{if(active)setTowns(value);}).catch(failure);return()=>{active=false;};},[state]);
  useEffect(()=>{if(view!=='explore')return;const id=++searchVersion.current;const timer=setTimeout(()=>{
    setBusy(true);const params=new URLSearchParams({q:query,kind,state,municipality_id:town,page:String(page),limit:'30'});for(const[key,value]of [...params])if(!value)params.delete(key);if(bbox)params.set('bbox',bbox);
    api<{items:Place[];total:number}>('/places?'+params).then(result=>{if(id===searchVersion.current){setPlaces(result.items);setTotal(result.total);}}).catch(()=>{if(id===searchVersion.current)failure();}).finally(()=>{if(id===searchVersion.current)setBusy(false);});
  },220);return()=>{clearTimeout(timer);searchVersion.current++;};},[query,kind,state,town,bbox,page,view]);
  async function navigate(next:string){if(parseResourceRoute(window.location.hash)){window.history.replaceState(null,'',window.location.pathname+window.location.search);setResourceRoute('');}setView(next);setDetail(null);setNotice('');cancelDetails();
    if(next==='account'&&user)try{setMine(await api<Observation[]>('/observations/mine'));}catch{failure();}
    if(next==='review')try{setQueue(await api<Observation[]>('/review'));}catch{failure();}
  }
  async function select(id:string){
    setDetailBusy(true);setDetail(null);setHistory([]);setTab('service');setNotice('');
    await detailTask.current.run(async signal=>{
      const result=await Promise.all([api<Detail>('/places/'+ref(id),{signal}),api<History[]>('/places/'+ref(id)+'/history',{signal})]);
      if(result[0].place.id!==id)throw new Error('Mismatched place identity');
      return result;
    },{success:([d,h])=>{setDetail(d);setHistory(h);},failure:()=>failure(),settled:()=>setDetailBusy(false)});
  }
  function favorite(id:string){const next=favorites.includes(id)?favorites.filter(value=>value!==id):[...favorites,id];try{localStorage.setItem('bdt:favorites',JSON.stringify(next));setFavorites(next);}catch{setNotice('blockedStorage');}}
  function openRegion(id:string){setRegionId(id);navigate('region');}
  function SourceView({source}:{source:Source}){const url=safeReference(source.url);return <div className="source"><span className="eyebrow">{t('source')}</span><strong>{formatDataset(source.dataset,locale)}</strong><dl><dt>{t('reference')}</dt><dd>{formatReferenceDate(source.reference_date,locale)}</dd><dt>{t('collected')}</dt><dd>{new Date(source.collected_at).toLocaleDateString(locale)}</dd></dl>{url&&<a href={url} target="_blank" rel="noopener noreferrer">{t('sourceOriginal')} ↗</a>}<details><summary>SHA-256</summary><code>{source.snapshot_sha256}</code></details></div>;}
  function MoneyCards({events}:{events:Money[]}){return events.length?<div className="money-grid">{events.map((event,index)=><article className="money" key={event.source.dataset+event.id+index}><span className="pill">{t(event.phase)}</span><h3>{money(event.cents,locale)}</h3><dl><dt>{t('instrument')}</dt><dd>{event.instrument_id}</dd><dt>{t('recipient')}</dt><dd>{event.recipient}</dd><dt>{t('period')}</dt><dd>{event.period}</dd></dl><SourceView source={event.source}/></article>)}</div>:<p className="empty">{t('financeEmpty')}</p>;}
  function Cards({items}:{items:Place[]}){
    function copyPlaceId(id:string){
      if(navigator.clipboard?.writeText)navigator.clipboard.writeText(id).catch(()=>{});
      setNotice('idCopied');
    }
    function focusPlace3D(place:Place){
      if(place.latitude!==null&&place.longitude!==null){
        setFocusCoords([place.longitude,place.latitude]);
        const mapEl=document.querySelector('.map-panel');
        if(mapEl)mapEl.scrollIntoView({behavior:'smooth',block:'nearest'});
      }
    }
    return <div className="place-list">{items.map(place=><article className="place-card" key={place.id}><div className={'kind-icon '+place.kind} aria-hidden="true">{place.kind==='school'?'▤':place.kind==='health'?'+':'◇'}</div><div className="card-main"><div className="card-top-meta"><span className="eyebrow">{t(place.kind)} · {place.state}</span>{place.latitude!==null?<span className="pill geo-pill">⌖ {t('geocodedBadge')}</span>:<span className="pill quiet-pill">⊘ {t('notGeocodedBadge')}</span>}</div><h2><button className="text-button" onClick={()=>select(place.id)}>{place.name}</button></h2><p>{place.address||<span className="quiet-text">📍 {t('noAddress')}</span>}</p>{place.phone&&<div className="card-phone"><span>📞</span> {place.phone}</div>}{place.declared_services.length>0&&<div className="card-services">{place.declared_services.slice(0,3).map(s=><span className="pill service-pill" key={s}>{t(s)}</span>)}</div>}<div className="card-bottom-bar"><small className="card-source-meta"><strong className="source-name">{formatDataset(place.source.dataset,locale)}</strong><span className="source-status"> · {formatReferenceDate(place.source.reference_date,locale)}</span></small><div className="card-actions"><button className="copy-pill" title={t('copyId')} aria-label={t('copyId')} onClick={()=>copyPlaceId(place.id)}>📋 {place.id.split(':')[1]||place.id}</button>{place.latitude!==null&&place.longitude!==null&&<button className="btn-map-3d" onClick={()=>focusPlace3D(place)} title={t('viewOnMap')} aria-label={t('viewOnMap')}>◩ {t('viewOnMap')}</button>}</div></div></div><button className="save-icon" aria-label={t(favorites.includes(place.id)?'unsave':'save')+' '+place.name} aria-pressed={favorites.includes(place.id)} onClick={()=>favorite(place.id)}>{favorites.includes(place.id)?'★':'☆'}</button></article>)}</div>;
  }
  function ObservationCards({rows}:{rows:Observation[]}){return <div className="observations">{rows.map(row=><article key={row.id}><span className="pill">{t(row.status==='pending'?'pendingLabel':row.status==='withdrawn'?'observationWithdrawn':row.status)}</span><p className="observation-body">{row.observation.body}</p><ObservationDownloads row={row} locale={locale}/><small>{t(row.observation.mode)} · {row.observation.observed_on}</small>{safeReference(row.observation.reference_url)&&<p><a href={safeReference(row.observation.reference_url)!} target="_blank" rel="noopener noreferrer">{t('referenceUrl')} ↗</a></p>}</article>)}</div>;}
  async function authentication(event:React.FormEvent<HTMLFormElement>,register=false){event.preventDefault();const data=new FormData(event.currentTarget);setBusy(true);setNotice('');try{const body=JSON.stringify({username:data.get('username'),password:data.get('password')});if(register){await api('/auth/register',{method:'POST',body});setNotice('registered');}else{setUser(await api<User>('/auth/login',{method:'POST',body}));setMine(await api('/observations/mine'));}}catch{failure();}finally{setBusy(false);}}
  async function submitObservation(event:React.FormEvent<HTMLFormElement>){event.preventDefault();if(!detail)return;const form=event.currentTarget,data=new FormData(form);setBusy(true);try{await api('/observations',{method:'POST',body:JSON.stringify({place_id:detail.place.id,mode:data.get('mode'),observed_on:data.get('observed_on'),body:data.get('body'),reference_url:data.get('reference_url')||null,consent:data.get('consent')==='on'})});setNotice('pending');form.reset();}catch{failure();}finally{setBusy(false);}}
  async function review(event:React.FormEvent<HTMLFormElement>,id:string){event.preventDefault();const data=new FormData(event.currentTarget);try{await api('/review/'+id,{method:'POST',body:JSON.stringify({decision:data.get('decision'),note:data.get('note')})});setQueue(await api('/review'));}catch{failure();}}
  const current=detail?.place;
  return <><a className="skip" href="#main">{t('explore')}</a><header className="header"><button className="brand" onClick={()=>navigate('explore')} aria-label="Brasil de Todos"><CivicLogo size={36} className="civic-brand-logo" /><span>Brasil<span className="brand-sub">de Todos</span></span></button><nav aria-label={t('explore')}>{['explore','saved','region','resources','groups','coverage'].map(value=><button key={value} className={view===value?'active':''} onClick={()=>navigate(value)}>{t(value)}</button>)}</nav><div className="header-right"><select aria-label="Idioma / Language / Idioma" value={locale} onChange={event=>setLocale(event.target.value as Locale)}><option value="pt-BR">Português (BR)</option><option value="en">English (US)</option><option value="es">Español</option></select><button onClick={()=>navigate('account')}>{user?.username||t('account')}</button>{user?.role==='reviewer'&&<><button onClick={()=>navigate('review')}>{t('review')}</button><button onClick={()=>navigate('workbench')}>{t('workbench')}</button></>}</div></header>
  <main id="main">{notice&&<div className="notice" role="status">{t(notice)}<button aria-label={t('close')} onClick={()=>setNotice('')}>×</button></div>}
  {detailBusy&&<div className="detail-request-status" role="status"><span>{t('loadingPlace')}</span><button onClick={cancelDetails}>{t('cancelPlace')}</button></div>}
  {current&&detail?<section className="detail"><button onClick={()=>{setDetail(null);cancelDetails();}} className="back">← {t('back')}</button><div className="detail-title"><div><span className="eyebrow">{t(current.kind)} · {current.state}</span><h1>{current.name}</h1><p>{current.address||t('noAddress')}</p></div><button className="primary" aria-pressed={favorites.includes(current.id)} onClick={()=>favorite(current.id)}>{t(favorites.includes(current.id)?'unsave':'save')}</button></div>{!current.catalogue_eligible&&<p className="callout">{t('withdrawn')}</p>}<div className="tabs" role="tablist" aria-label={t('details')}>{['service','finance','history','community','source'].map(value=><button key={value} role="tab" aria-selected={tab===value} aria-controls={'tabpanel-'+value} className={tab===value?'active':''} onClick={()=>setTab(value)}>{t(value==='service'?'details':value)}</button>)}</div>
  {tab==='service'&&<div role="tabpanel" id="tabpanel-service" className="detail-columns"><article className="panel"><p className="callout">{t('serviceNote')}</p><h2>{t('details')}</h2>{current.phone&&<p>{current.phone}</p>}<div className="tags">{current.declared_services.map(service=><span className="pill" key={service}>{t(service)}</span>)}</div>{current.latitude===null&&<p>{t('noGeo')}</p>}<button onClick={()=>openRegion(current.municipality_id)}>{t('region')} →</button></article><SourceView source={current.source}/></div>}
  {tab==='finance'&&<div role="tabpanel" id="tabpanel-finance"><p className="callout">{t('regionNote')}</p><MoneyCards events={detail.finance}/><PlaceEvidence placeId={current.id} t={t}/><button onClick={()=>openRegion(current.municipality_id)}>{t('region')} →</button></div>}
  {tab==='source'&&<div role="tabpanel" id="tabpanel-source"><SourceView source={current.source}/><p>{t('placeIdentifier')}: <code>{current.id}</code></p><button onClick={()=>downloadJSON('brasildetodos-'+current.id.replace(':','-')+'.json',detail)}>{t('exportData')}</button></div>}
  {tab==='history'&&<div role="tabpanel" id="tabpanel-history" className="timeline">{history.length?history.map((entry,index)=><article key={entry.at+index}><span className="eyebrow">{new Date(entry.at).toLocaleString(locale)}</span><h2>{t(entry.type)}</h2>{entry.type==='updated'&&<><p>{entry.fields.join(', ')}</p><details><summary>{t('source')}</summary><pre>{JSON.stringify({before:entry.before,after:entry.after},null,2)}</pre></details></>}</article>):<p>{t('historyEmpty')}</p>}</div>}
  {tab==='community'&&<div role="tabpanel" id="tabpanel-community"><h2>{t('community')}</h2>{detail.observations.length?<ObservationCards rows={detail.observations}/>:<p>{t('noCommunity')}</p>}<div className="panel"><h2>{t('contribute')}</h2><p>{t('observationNote')}</p>{user&&<GuidedVisit key={current.id} place={current} locale={locale}/>}<p>{t('mode')}</p>{!user?<button onClick={()=>navigate('account')}>{t('login')}</button>:<form onSubmit={submitObservation}><label>{t('mode')}<select name="mode" required><option value="field">{t('field')}</option><option value="document">{t('document')}</option><option value="street_image">{t('street_image')}</option></select></label><label>{t('when')}<input name="observed_on" type="date" required max={new Date().toISOString().slice(0,10)}/></label><label>{t('observation')}<textarea name="body" minLength={20} maxLength={1200} required rows={4}/></label><label>{t('referenceUrl')}<input type="url" name="reference_url" maxLength={2000}/></label><label className="check"><input type="checkbox" name="consent" required/>{t('consent')}</label><button className="primary" disabled={busy}>{t('submit')}</button></form>}</div></div>}
  </section>:<>
  {view==='explore'&&<><section className="hero"><span className="eyebrow">{t('heroEyebrow')}</span><h1>{t('tagline')}</h1><p>{t('intro')}</p><div className="hero-stats"><div className="hero-stat-card"><strong>{(234209).toLocaleString(locale)}</strong><span>{t('nationalFacilities')}</span></div><div className="hero-stat-card"><strong>{(5570).toLocaleString(locale)}</strong><span>{t('coverageMunicipalities')}</span></div><div className="hero-stat-card"><strong>{(63930).toLocaleString(locale)}+</strong><span>{t('financialEventsMapped')}</span></div><div className="hero-stat-card"><strong>{t('view3DExplorationBadge')}</strong><span>{t('view3DExploration')}</span></div></div></section><section className="filters" aria-label={t('search')}><label className="search-label"><span>{t('search')}</span><input type="search" placeholder={t('search')} value={query} maxLength={200} onChange={event=>{setQuery(event.target.value);setPage(1);}}/></label><label><span>{t('states')}</span><select value={state} onChange={event=>{setState(event.target.value);setTown('');setBbox('');setPage(1);}}><option value="">{t('states')}</option>{states.map(value=><option key={value}>{value}</option>)}</select></label><label><span>{t('towns')}</span><select value={town} onChange={event=>{setTown(event.target.value);setBbox('');setPage(1);}}><option value="">{t('towns')}</option>{towns.map(value=><option key={value.id} value={value.id}>{value.name} · {value.state}</option>)}</select></label><button onClick={()=>{setQuery('');setTown('');setState('');setKind('');setBbox('');setPage(1);}}>{t('clear')}</button></section><div className="category-tabs">{['','school','health','work'].map(value=><button key={value} aria-pressed={kind===value} className={kind===value?'selected':''} onClick={()=>{setKind(value);setPage(1);}}>{t(value||'all')}</button>)}</div><div className="explorer"><section aria-live="polite" aria-busy={busy}><div className="results-heading"><strong>{busy?t('loading'):total.toLocaleString(locale)+' '+t('records')}</strong>{bbox&&<button onClick={()=>setBbox('')}>{t('clear')} ⌖</button>}</div>{places.length?<Cards items={places}/>:!busy&&<div className="empty"><h2>{t('empty')}</h2><p>{t('emptyHelp')}</p><button onClick={()=>navigate('coverage')}>{t('coverage')}</button></div>}<div className="pager"><button disabled={page===1} onClick={()=>setPage(value=>value-1)}>{t('prev')}</button><span>{page}</span><button disabled={page*30>=total} onClick={()=>setPage(value=>value+1)}>{t('next')}</button></div></section><MapView locale={locale} places={places} select={select} t={t} filters={{q:query,kind,state,municipality_id:town}} onBounds={bounds=>{setBbox(bounds);setPage(1);}} focusCoordinates={focusCoords}/></div></>}
  {view==='resources'&&<Resources t={t} locale={locale} routeHash={resourceRoute}/>}
  {view==='saved'&&<SavedPlaces ids={favorites} locale={locale} t={t} onSelect={select} onRemove={favorite} onExplore={()=>navigate('explore')}/>}
  {view==='region'&&<Region initialId={regionId} locale={locale} t={t} renderMoney={events=><MoneyCards events={events}/>} onExplore={(id,category)=>{setTown(id);setState('');setKind(category);setQuery('');setBbox('');setPage(1);navigate('explore');}}/>}
  {view==='groups'&&<Groups user={user} locale={locale} t={t} onLogin={()=>navigate('account')} onSelect={select}/>}
  {view==='coverage'&&<CatalogCoverage locale={locale} t={t}/>}
  {view==='account'&&<section className="page narrow"><h1>{t('account')}</h1><p>{t('authNote')}</p>{user?<><p><strong>{user.username}</strong></p><button onClick={async()=>{try{await api('/auth/logout',{method:'POST'});setUser(null);setMine([]);}catch{failure();}}}>{t('logout')}</button><h2>{t('myContributions')}</h2><ObservationCards rows={mine}/><PrivacyControls rows={mine} t={t} onChange={()=>{api<Observation[]>('/observations/mine').then(setMine).catch(failure);}} onDeleted={()=>{setUser(null);setMine([]);}}/></>:<form className="panel" onSubmit={authentication}><label>{t('username')}<input name="username" autoComplete="username" pattern="[a-zA-Z0-9_-]{3,40}" required/></label><label>{t('password')}<input name="password" type="password" autoComplete="current-password" minLength={12} maxLength={128} required/></label><button className="primary" disabled={busy}>{t('login')}</button>{config?.registration_enabled?<button disabled={busy} type="button" onClick={event=>{const form=event.currentTarget.form;if(form?.reportValidity())authentication({preventDefault(){},currentTarget:form} as React.FormEvent<HTMLFormElement>,true);}}>{t('register')}</button>:<p>{t('registrationOff')}</p>}</form>}</section>}
  {view==='review'&&user?.role==='reviewer'&&<section className="page"><h1>{t('review')}</h1>{queue.length?queue.map(row=><article className="panel" key={row.id}><button onClick={()=>select(row.place_id)}>{row.place_id}</button><ObservationCards rows={[row]}/><form onSubmit={event=>review(event,row.id)}><label>{t('reviewNote')}<textarea required name="note" minLength={10} maxLength={1000}/></label><select name="decision" aria-label={t('review')}><option value="approved">{t('approve')}</option><option value="rejected">{t('reject')}</option></select><button className="primary">{t('submit')}</button></form></article>):<p>{t('noReview')}</p>}</section>}
  {view==='workbench'&&user?.role==='reviewer'&&<Workbench t={t}/>}
  </>}
  </main><footer><div><strong>Brasil de Todos</strong><p>{t('independent')}</p></div><div><a href={safeReference(config?.source_code)||'https://github.com/rafaelob/brasildetodos'} target="_blank" rel="noopener noreferrer">{t('code')} ↗</a><p>AGPL-3.0-or-later · {t('noLLM')}</p></div></footer></>;
}
createRoot(document.getElementById('root')!).render(<StrictMode><App/></StrictMode>);
