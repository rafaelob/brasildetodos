// SPDX-License-Identifier: AGPL-3.0-or-later
import {favoriteIds,isPlaceId} from './watch-state.mjs';
export const COMPARISON_LIMIT=3;
export const comparisonText={
 'pt-BR': {title:'Comparar lugares salvos',intro:'Compare informações declaradas antes de entrar em contato. Não é ranking de qualidade, disponibilidade de vagas ou garantia de atendimento.',select:'Selecionar para comparação',selected:'lugares selecionados',limit:'Selecione de dois a três lugares. A seleção fica nesta tela e não é publicada.',open:'Abrir comparação',close:'Fechar comparação',clear:'Limpar seleção',retry:'Tentar comparação novamente',failure:'Não foi possível carregar a comparação. Seus lugares salvos continuam disponíveis.',empty:'Selecione pelo menos dois lugares para comparar.',missing:'Informação não disponível nesta instalação',outside:'Fora do perfil atual do catálogo; confirme a situação na fonte.',name:'Nome declarado',kind:'Tipo',school:'Escola',health:'Saúde',work:'Obra',address:'Endereço declarado',phone:'Contato informado',services:'Serviços declarados',state:'UF',municipality:'Código do município',reference:'Referência temporal',collected:'Coletado em',source:'Abrir fonte',details:'Consultar ficha',noPhone:'Contato não informado',noAddress:'Endereço não informado',noServices:'Oferta não informada; confirme com a unidade.',unknown:'Não informado',mixed:'Os tipos de lugares diferem. Compare dados cadastrais, não resultados de serviços distintos.',dates:'Fontes e períodos podem ser diferentes. Não tratamos ausência de informação como ausência de serviço.',refresh:'Atualizar comparação'},
 'en': {title:'Compare saved places',intro:'Compare declared information before contacting a service. This is not a quality ranking, availability report or guarantee of care.',select:'Select for comparison',selected:'places selected',limit:'Select two or three places. The selection stays on this screen and is not published.',open:'Open comparison',close:'Close comparison',clear:'Clear selection',retry:'Retry comparison',failure:'The comparison could not be loaded. Your saved places remain available.',empty:'Select at least two places to compare.',missing:'Information unavailable in this installation',outside:'Outside the current catalog profile; confirm its status at the source.',name:'Declared name',kind:'Type',school:'School',health:'Health',work:'Construction',address:'Declared address',phone:'Reported contact',services:'Declared services',state:'State',municipality:'Municipality code',reference:'Reference date',collected:'Collected at',source:'Open source',details:'View place',noPhone:'Contact not provided',noAddress:'Address not provided',noServices:'Service offering not provided; confirm with the establishment.',unknown:'Not provided',mixed:'These are different types of places. Compare registry information, not outcomes of unrelated services.',dates:'Sources and reference periods may differ. Missing information does not mean the service is absent.',refresh:'Refresh comparison'},
 'es': {title:'Comparar lugares guardados',intro:'Compare la información declarada antes de contactar al servicio. No es una clasificación de calidad, disponibilidad ni garantía de atención.',select:'Seleccionar para comparar',selected:'lugares seleccionados',limit:'Seleccione dos o tres lugares. La selección permanece en esta pantalla y no se publica.',open:'Abrir comparación',close:'Cerrar comparación',clear:'Limpiar selección',retry:'Reintentar comparación',failure:'No se pudo cargar la comparación. Sus lugares guardados siguen disponibles.',empty:'Seleccione al menos dos lugares para comparar.',missing:'Información no disponible en esta instalación',outside:'Fuera del perfil actual del catálogo; confirme su situación en la fuente.',name:'Nombre declarado',kind:'Tipo',school:'Escuela',health:'Salud',work:'Obra',address:'Dirección declarada',phone:'Contacto informado',services:'Servicios declarados',state:'Estado',municipality:'Código municipal',reference:'Fecha de referencia',collected:'Recopilado en',source:'Abrir fuente',details:'Consultar ficha',noPhone:'Contacto no informado',noAddress:'Dirección no informada',noServices:'Oferta no informada; confirme con la unidad.',unknown:'No informado',mixed:'Los tipos de lugares son distintos. Compare datos de registro, no resultados de servicios diferentes.',dates:'Las fuentes y períodos pueden ser diferentes. La falta de información no significa ausencia del servicio.',refresh:'Actualizar comparación'},
};
export function comparisonSelection(chosen,available) {
 const allowed=new Set(favoriteIds(available));
 return favoriteIds(chosen).filter(id=>allowed.has(id)).slice(0,COMPARISON_LIMIT);
}
export function toggleComparison(chosen,id,available) {
 const next=comparisonSelection(chosen,available);
 if(next.includes(id))return next.filter(value=>value!==id);
 if(!isPlaceId(id)||!favoriteIds(available).includes(id)||next.length===COMPARISON_LIMIT)return next;
 return [...next,id];
}
/** Validate order/identity before rendering: a response cannot label one unit as another. */
export function comparisonItems(payload,ids) {
 if(!payload||!Array.isArray(payload.items)||payload.items.length!==ids.length)throw new Error('comparison_count_mismatch');
 if(ids.length<2||ids.length>COMPARISON_LIMIT||new Set(ids).size!==ids.length)throw new Error('comparison_selection_invalid');
 const allowed=new Set(['available','outside_current_profile','not_found','unavailable']);
 return ids.map((id,index)=>{
  const row=payload.items[index];
  if(!row||row.id!==id||!allowed.has(row.status))throw new Error('comparison_identity_mismatch');
  if(row.place!==null) {
   if(!row.place||row.place.id!==id||!['school','health','work'].includes(row.place.kind)||!row.place.source||typeof row.place.name!=='string'||!Array.isArray(row.place.declared_services)||row.place.declared_services.some(v=>typeof v!=='string'))throw new Error('comparison_place_invalid');
   if(['not_found','unavailable'].includes(row.status))throw new Error('comparison_status_conflict');
  }else if(['available','outside_current_profile'].includes(row.status))throw new Error('comparison_status_conflict');
  return row;
 });
}
