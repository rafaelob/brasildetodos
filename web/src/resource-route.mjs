// Only user-selected public search criteria enter a shared link. No copying of
// location.search, account tokens, favorites, GPS, or arbitrary hash parameters.
export const resourceProviders=['pncp_contracts','transferegov_special_plans','obrasgov_projects'];
const states=new Set('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split(' '));
const locales=new Set(['pt-BR','en','es']);
const clean=value=>typeof value==='string'&&!/[\u0000-\u001f\u007f]/.test(value)?value:'';
export function normalizeResourceRoute(value={}) {
  const q=clean(value.q),municipality=clean(value.municipality),id=clean(value.id);
  return {q:q.length<=200?q:'',profile:resourceProviders.includes(value.profile)?value.profile:'',
    state:states.has(value.state)?value.state:'',municipality:/^\d{7}$/.test(municipality)?municipality:'',
    id:/^[a-z0-9_-]+:[A-Za-z0-9._/\-]+$/.test(id)&&id.length<=200?id:'',
    locale:locales.has(value.locale)?value.locale:'pt-BR'};
}
export function parseResourceRoute(hash) {
  if(typeof hash!=='string'||hash.length>3000||!/^#resources(?:\?|$)/.test(hash))return null;
  const params=new URLSearchParams(hash.slice('#resources'.length).replace(/^\?/,''));
  const value={};
  for(const key of ['q','profile','state','municipality','id','locale']) {
    const values=params.getAll(key);
    if(values.length>1)return null;
    value[key]=values[0]||'';
  }
  return normalizeResourceRoute(value);
}
export function resourceHash(value={}) {
  const params=new URLSearchParams();
  for(const[key,item]of Object.entries(normalizeResourceRoute(value)))if(item)params.set(key,item);
  return '#resources?'+params.toString();
}
export function resourceShareURL(base,value={}) {
  const url=new URL(base);
  if(!['http:','https:'].includes(url.protocol)||url.username||url.password)throw new Error('invalid_share_origin');
  return url.origin+url.pathname+resourceHash(value);
}
