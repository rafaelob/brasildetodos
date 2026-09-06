// SPDX-License-Identifier: AGPL-3.0-or-later
import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import {groupText} from './group-text.mjs';
import {groupFailure,taskActions,taskPage,validToken} from './group-tools.mjs';
import {ConfirmAction,NewGroupTask,SubmitGroupTask} from './GroupForms';
import type {Locale,Observation,User} from './types';
import './groups.css';
type Group={id:string;name:string;description:string;status:string;revision:number;owner:boolean;visibility:'private';created_at:string};
type Member={id:string;username:string;owner:boolean;me:boolean};
type Task={id:string;place_id:string;place_name:string|null;title:string;instructions:string;state:string;effective_state:string;revision:number;assigned_to_me:boolean;created_by_me:boolean;can_review:boolean;observation:Observation|null;review_note:string|null};
type Detail={group:Group;members:Member[];invites:{id:string;expires_at:number}[];tasks:{items:Task[];total:number;page:number;limit:number};public:false};
export default function GroupsPage({locale,user,onLogin,onOpenPlace}:{locale:Locale;user:User|null;onLogin:()=>void;onOpenPlace:(id:string)=>void}) {
 const t=(key:string)=>groupText(locale,key),[selected,setSelected]=useState(''),[items,setItems]=useState<Group[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState(''),[refresh,setRefresh]=useState(0),[busy,setBusy]=useState(false);
 const alive=useRef(true),locked=useRef(false);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{if(!user)return;let active=true;const controller=new AbortController();setLoading(true);setError('');
  api<{items:Group[]}>('/groups',{signal:controller.signal}).then(data=>{if(active)setItems(data.items);}).catch(e=>{if(active)setError(groupFailure(e));}).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;controller.abort();};
 },[user?.username,refresh]);
 async function create(path:string,body:unknown){
  if(locked.current)return false;locked.current=true;setBusy(true);setError('');
  try{const group=await api<Group>(path,{method:'POST',body:JSON.stringify(body)});if(alive.current){setSelected(group.id);setRefresh(x=>x+1);}return true;}
  catch(e){if(alive.current)setError(groupFailure(e));return false;}finally{locked.current=false;if(alive.current)setBusy(false);}
 }
 if(!user)return <section className="page groups-page"><h1>{t('heading')}</h1><p>{t('intro')}</p><p>{t('loginRequired')}</p><button onClick={onLogin}>{t('login')}</button></section>;
 if(selected)return <GroupWorkspace key={user.username+selected} id={selected} locale={locale} onBack={()=>{setSelected('');setRefresh(x=>x+1);}} onOpenPlace={onOpenPlace}/>;
 return <section className="page groups-page"><header><span className="eyebrow">BRASIL DE TODOS</span><h1>{t('heading')}</h1><p>{t('intro')}</p></header>
  {error&&<p role="alert">{t(error)}</p>}
  <button onClick={()=>setRefresh(x=>x+1)} disabled={loading||busy}>{t('retry')}</button>
  <div className="groups-layout"><div className="group-directory" aria-live="polite" aria-busy={loading}>
   {loading?<p>{t('loading')}</p>:items.length?items.map(group=><article className="panel" key={group.id}><span className="pill">{t(group.status)}</span><h2><button className="text-button" onClick={()=>setSelected(group.id)}>{group.name}</button></h2><p>{group.description}</p><small>{t('private')}</small></article>):!error&&<p>{t('empty')}</p>}
  </div><aside className="group-start"><section className="panel"><h2>{t('create')}</h2><form onSubmit={async e=>{e.preventDefault();const form=e.currentTarget,data=new FormData(form);if(await create('/groups',{name:data.get('name'),description:data.get('description')}))form.reset();}}>
   <label>{t('name')}<input name="name" minLength={3} maxLength={120} required/></label><label>{t('description')}<textarea name="description" maxLength={1000} rows={3}/></label><button disabled={busy}>{t('create')}</button>
  </form></section><section className="panel"><h2>{t('join')}</h2><form onSubmit={async e=>{e.preventDefault();const form=e.currentTarget,data=new FormData(form),token=String(data.get('token')||'').trim();if(!validToken(token)){setError('invalid');return;}if(await create('/groups/join',{token,consent:data.get('consent')==='on'}))form.reset();}}>
   <label>{t('token')}<input name="token" type="password" required minLength={43} maxLength={43} autoComplete="off" spellCheck={false}/></label><label className="check"><input name="consent" type="checkbox" required/>{t('joinConsent')}</label><button disabled={busy}>{t('join')}</button>
  </form></section></aside></div>
 </section>;
}
function GroupWorkspace({id,locale,onBack,onOpenPlace}:{id:string;locale:Locale;onBack:()=>void;onOpenPlace:(id:string)=>void}) {
 const t=(key:string)=>groupText(locale,key),[data,setData]=useState<Detail|null>(null),[page,setPage]=useState(1),[refresh,setRefresh]=useState(0),[loading,setLoading]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [token,setToken]=useState<{token:string;expires_at:number}|null>(null),alive=useRef(true),locked=useRef(false);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{let active=true;const controller=new AbortController();setLoading(true);
  api<Detail>('/groups/'+encodeURIComponent(id)+'?page='+page,{signal:controller.signal}).then(value=>{if(active){const adjusted=taskPage(page,value.tasks.total);if(adjusted!==page){setPage(adjusted);return;}setData(value);}})
   .catch(e=>{if(active){setData(null);setToken(null);setError(groupFailure(e));}}).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;controller.abort();};
 },[id,page,refresh]);
 async function write(path:string,body:Record<string,unknown>,success?:(value:any)=>void){
  if(locked.current||!data||loading)return false;locked.current=true;setBusy(true);setError('');setNotice('');
  try{const result=await api<any>('/groups/'+encodeURIComponent(id)+path,{method:'POST',body:JSON.stringify({expected_revision:data.group.revision,...body})});
   if(alive.current){success?.(result);setNotice('saved');setRefresh(x=>x+1);}return true;
  }catch(e){if(alive.current){setError(groupFailure(e));if(/HTTP (401|403|404)/.test(String(e))){setData(null);setToken(null);}}return false;}
  finally{locked.current=false;if(alive.current)setBusy(false);}
 }
 const blocked=busy||loading||Boolean(error),group=data?.group,active=group?.status==='active';
 return <section className="page groups-page"><button onClick={onBack}>{t('back')}</button><div className="group-toolbar"><button disabled={busy} onClick={()=>{setError('');setNotice('');setRefresh(x=>x+1);}}>{t('retry')}</button>{loading&&<span role="status">{t('loading')}</span>}</div>
  {error&&<p role="alert">{t(error)}</p>}{notice&&<p role="status">{t(notice)}</p>}
  {data&&group&&<><header><span className="pill">{t('private')} · {t(group.status)}</span><h1>{group.name}</h1><p>{group.description}</p><small>{t('revision')}: {group.revision}</small></header>
   <p className="callout">{t('reviewDisclaimer')}</p>
   <div className="groups-layout"><div className="group-task-column"><h2>{t('tasks')} ({data.tasks.total})</h2>
    {active&&<NewGroupTask locale={locale} disabled={blocked} create={body=>write('/tasks',body as Record<string,unknown>)}/>}
    <div className="group-task-list" aria-busy={loading}>{data.tasks.items.length?data.tasks.items.map(task=><GroupTask key={task.id} task={task} owner={group.owner} active={Boolean(active)} locale={locale} disabled={blocked} action={body=>write('/tasks/'+task.id,body)} onOpenPlace={onOpenPlace}/>):<p>{t('noTasks')}</p>}</div>
    <nav className="pager" aria-label={t('tasks')}><button disabled={page===1||busy||loading} onClick={()=>setPage(x=>x-1)}>{t('previous')}</button><span>{t('page')} {page}</span><button disabled={page*20>=data.tasks.total||busy||loading} onClick={()=>setPage(x=>x+1)}>{t('next')}</button></nav>
   </div><aside className="group-management">
    {group.owner&&active&&<details className="panel"><summary>{t('edit')}</summary><form key={group.revision} onSubmit={async e=>{e.preventDefault();const form=new FormData(e.currentTarget);await write('/edit',{name:form.get('name'),description:form.get('description')});}}><label>{t('name')}<input name="name" minLength={3} maxLength={120} required defaultValue={group.name}/></label><label>{t('description')}<textarea name="description" maxLength={1000} rows={3} defaultValue={group.description}/></label><button disabled={blocked}>{t('save')}</button></form></details>}
    <section className="panel"><h2>{t('members')} ({data.members.length})</h2>{data.members.map(member=><article className="group-member" key={member.id}><strong>{member.username}</strong><small>{member.owner?t('owner'):''} {member.me?t('you'):''}</small>{group.owner&&!member.me&&active&&<div className="group-actions"><ConfirmAction locale={locale} label={t('remove')} help={t('confirmHelp')} disabled={blocked} run={()=>write('/members/remove',{user_id:member.id})}/><ConfirmAction locale={locale} label={t('transfer')} help={t('confirmHelp')} disabled={blocked} run={()=>write('/transfer',{user_id:member.id},()=>setToken(null))}/></div>}</article>)}</section>
    {group.owner&&active&&<section className="panel group-invites"><h2>{t('invites')}</h2><button disabled={blocked} onClick={()=>write('/invites',{},value=>setToken({token:value.token,expires_at:value.expires_at}))}>{t('newInvite')}</button>{token&&<div className="group-secret"><p>{t('inviteHint')}</p><label>{t('token')}<textarea className="group-token" value={token.token} readOnly rows={2} spellCheck={false}/></label><p>{t('expires')}: {new Date(token.expires_at*1000).toLocaleString(locale)}</p><button onClick={()=>setToken(null)}>{t('hideToken')}</button></div>}{data.invites.length?data.invites.map(invite=><article key={invite.id}><span>{t('expires')}: {new Date(invite.expires_at*1000).toLocaleString(locale)}</span><button disabled={blocked} onClick={()=>write('/invites/'+invite.id+'/revoke',{},()=>setToken(null))}>{t('revoke')}</button></article>):<p>{t('noInvites')}</p>}</section>}
    <section className="panel group-actions">{group.owner&&active?<ConfirmAction locale={locale} label={t('archive')} help={t('archiveHelp')} disabled={blocked} run={()=>write('/archive',{},()=>setToken(null))}/>:<ConfirmAction locale={locale} label={t('leave')} help={t('leaveHelp')} disabled={blocked} run={()=>write('/leave',{},onBack)}/>}</section>
   </aside></div>
  </>}
 </section>;
}
function GroupTask({task,owner,active,locale,disabled,action,onOpenPlace}:{task:Task;owner:boolean;active:boolean;locale:Locale;disabled:boolean;action:(body:Record<string,unknown>)=>Promise<boolean>;onOpenPlace:(id:string)=>void}) {
 const t=(key:string)=>groupText(locale,key),actions=taskActions(task,owner,active),[note,setNote]=useState('');
 return <article className="panel group-task"><span className="pill group-task-state">{t(task.effective_state)}</span><h3>{task.title}</h3><button className="text-button" onClick={()=>onOpenPlace(task.place_id)}>{t('openPlace')}: {task.place_name||task.place_id}</button><p className="group-prose">{task.instructions}</p>
  <div className="group-actions">{actions.filter(a=>['claim','release','reopen'].includes(a)).map(a=><button key={a} disabled={disabled} onClick={()=>action({action:a})}>{t(a)}</button>)}{actions.includes('cancel')&&<ConfirmAction locale={locale} label={t('cancel')} help={t('reviewDisclaimer')} disabled={disabled} run={()=>action({action:'cancel'})}/>}</div>
  {task.observation&&<section className="group-evidence"><h4>{t('observation')}</h4><p className="group-prose">{task.observation.observation.body}</p><small>{task.observation.observation.observed_on} · {t(task.observation.status)}</small><p>{t('privateObservation')}</p></section>}
  {task.review_note&&<p className="group-prose">{t('reviewNote')}: {task.review_note}</p>}
  {actions.includes('submit')&&<SubmitGroupTask locale={locale} placeId={task.place_id} disabled={disabled} submit={action}/>}
  {actions.includes('accept')&&<form className="group-review" onSubmit={e=>e.preventDefault()}><label>{t('reviewNote')}<textarea required minLength={10} maxLength={1000} value={note} onChange={e=>setNote(e.target.value)} rows={3}/></label><div className="group-actions">{['accept','request_changes'].map(a=><button key={a} type="button" disabled={disabled||note.trim().length<10} onClick={async()=>{if(await action({action:a,note}))setNote('');}}>{t(a)}</button>)}</div></form>}
 </article>;
}
