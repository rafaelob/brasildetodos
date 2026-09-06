export type Locale = 'pt-BR' | 'en' | 'es';
export type Source = {dataset:string; url:string; record_id:string; reference_date:string|null; collected_at:string; snapshot_sha256:string};
export type Place = {id:string; kind:'school'|'health'|'work'; catalogue_eligible:boolean; name:string; state:string; municipality_id:string; address:string; phone:string|null; latitude:number|null; longitude:number|null; geo_source:string|null; declared_services:string[]; source:Source};
export type Observation = {id:string; place_id:string; status:'pending'|'approved'|'rejected'|'withdrawn'|'retracted'; created_at:string; reviewed_at:string|null; observation:{mode:string; observed_on:string; body:string; reference_url:string|null}};
export type Money = {id:string; phase:string; cents:number; source:Source; municipality_id:string; instrument_id:string; period:string; recipient:string; perspective:string; nature:string; currency:string};
export type Detail = {place:Place; finance:Money[]; observations:Observation[]};
export type User = {username:string; role:string};
