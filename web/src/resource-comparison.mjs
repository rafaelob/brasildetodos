// SPDX-License-Identifier: AGPL-3.0-or-later
import {amountFields,resourceAmounts} from './resource-i18n.mjs';
export const comparisonMessages={
 'pt-BR':{open:'Comparar com a versão anterior',close:'Fechar comparação',before:'Antes',after:'Depois',
  notice:'Diferenças entre versões observadas pela plataforma, não comprovação de execução. Valores permanecem separados por significado; não são somados. São mostrados apenas campos comparáveis.',
  none:'Nenhuma diferença nos campos comparáveis. Consulte as fontes e os identificadores do histórico.',
  unavailable:'Não há duas versões consecutivas e compatíveis para esta comparação.',source:'Fonte da versão',unknown:'Não informado'},
 en:{open:'Compare with the previous version',close:'Close comparison',before:'Before',after:'After',
  notice:'Differences between platform-observed versions, not proof of delivery. Amounts remain separate by meaning and are not added. Only comparable fields are shown.',
  none:'No differences in comparable fields. Check the sources and historical field identifiers.',
  unavailable:'Two consecutive compatible versions are not available for this comparison.',source:'Version source',unknown:'Not provided'},
 es:{open:'Comparar con la versión anterior',close:'Cerrar comparación',before:'Antes',after:'Después',
  notice:'Diferencias entre versiones observadas por la plataforma, no prueba de ejecución. Los importes permanecen separados por significado y no se suman. Solo se muestran campos comparables.',
  none:'Sin diferencias en los campos comparables. Consulta las fuentes y los identificadores del historial.',
  unavailable:'No hay dos versiones consecutivas y compatibles para esta comparación.',source:'Fuente de la versión',unknown:'No informado'}
};
export function comparisonText(locale,key){return (comparisonMessages[locale]??comparisonMessages['pt-BR'])[key]??key;}
const FIELDS=['title','kind','municipality_id','attributes.declared_status','attributes.buyer_name',
 'attributes.starts_on','attributes.ends_on','attributes.upstream_updated_at',
 'attributes.state','attributes.territorial_basis','attributes.budget_direction','source.reference_date'];
const record=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
function scalar(payload,key){
 const [head,tail]=key.split('.');const value=tail?payload[head]?.[tail]:payload[head];
 if(value===null||value===undefined)return null;
 if(typeof value!=='string'||value.length>50000)throw new TypeError('noncomparable_resource_field');
 return value;
}
function monetary(attributes){
 const values=new Map(resourceAmounts(attributes).map(item=>[item.key,item]));
 const precise=attributes.profile==='pncp_contracts'?attributes.precise_amounts:undefined;
 if(precise!==null&&precise!==undefined&&!record(precise))throw new TypeError('noncomparable_resource_amount');
 for(const key of Object.keys(amountFields)){
  const decimal=precise&&Object.hasOwn(precise,key.replace(/_cents$/,''));
  const raw=attributes[key];
  if((decimal&&raw!==null&&raw!==undefined)||((decimal||raw!==null&&raw!==undefined)&&!values.has(key)))
   throw new TypeError('noncomparable_resource_amount');
 }
 return values;
}
function exactKey(item){
 if(!item)return null;
 if(typeof item.decimal==='string'){
  const [whole,fraction]=item.decimal.split('.');return whole+'.'+fraction.padEnd(4,'0');
 }
 const value=BigInt(item.cents);return String(value/100n)+'.'+String(value%100n).padStart(2,'0')+'00';
}
/** Compare one identity only; never infer missing versions or monetary stages. */
export function compareResourceVersions(older,newer){
 const unavailable={status:'unavailable',changes:[]};
 if(!record(older)||!record(newer)||!Number.isSafeInteger(older.revision)||older.revision<1||
   !Number.isSafeInteger(newer.revision)||newer.revision!==older.revision+1)return unavailable;
 const before=older.resource,after=newer.resource;
 if(!record(before)||!record(after)||typeof before.id!=='string'||before.id!==after.id||
   !record(before.attributes)||!record(after.attributes)||!record(before.source)||!record(after.source)||
   before.attributes.profile!==after.attributes.profile||before.source.dataset!==after.source.dataset)return unavailable;
 try{
  const changes=[];
  for(const key of FIELDS){
   const a=scalar(before,key),b=scalar(after,key);
   if(a!==b)changes.push({key,kind:'text',before:a,after:b});
  }
  const a=monetary(before.attributes),b=monetary(after.attributes);
  for(const key of Object.keys(amountFields))if(exactKey(a.get(key))!==exactKey(b.get(key)))
   changes.push({key:'attributes.'+key,kind:'amount',before:a.get(key)??null,after:b.get(key)??null});
  return {status:'comparable',changes};
 }catch{return unavailable;}
}
