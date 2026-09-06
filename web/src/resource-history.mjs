// SPDX-License-Identifier: AGPL-3.0-or-later
import {resourceMessages} from './resource-i18n.mjs';
const labels={
 'pt-BR':{technical:'Identificadores dos campos na fonte',other:'Outro campo da fonte',title:'Objeto ou título',kind:'Tipo de registro',municipality:'Município relacionado',reference:'Data de referência',record:'Identificador na fonte',dataset:'Conjunto de dados',scope:'Abrangência territorial',state:'UF informada',precision:'Valores com precisão original',direction:'Receita ou despesa declarada'},
 en:{technical:'Field identifiers in the source',other:'Other source field',title:'Object or title',kind:'Record type',municipality:'Related municipality',reference:'Reference date',record:'Source identifier',dataset:'Dataset',scope:'Territorial scope',state:'Declared state',precision:'Amounts with original precision',direction:'Declared revenue or expenditure'},
 es:{technical:'Identificadores de campos en la fuente',other:'Otro campo de la fuente',title:'Objeto o título',kind:'Tipo de registro',municipality:'Municipio relacionado',reference:'Fecha de referencia',record:'Identificador en la fuente',dataset:'Conjunto de datos',scope:'Ámbito territorial',state:'Estado declarado',precision:'Importes con precisión original',direction:'Ingreso o gasto declarado'}
};
const basic={title:'title',kind:'kind',municipality_id:'municipality','source.reference_date':'reference','source.record_id':'record','source.dataset':'dataset','attributes.territorial_basis':'scope','attributes.state':'state','attributes.precise_amounts':'precision','attributes.budget_direction':'direction'};
const existing={'attributes.initial_cents':'resourceInitialAmount','attributes.global_cents':'resourceGlobalAmount','attributes.accumulated_cents':'resourceAccumulatedAmount','attributes.planned_operating_cents':'resourceOperatingAmount','attributes.planned_investment_cents':'resourceInvestmentAmount','attributes.planned_investments':'resourceProjectAmount','attributes.declared_status':'resourceStatus','attributes.buyer_name':'resourceBuyer','attributes.starts_on':'resourceStart','attributes.ends_on':'resourceEnd','attributes.upstream_updated_at':'resourceOfficialUpdate'};
export function historyText(locale,key){return (labels[locale]??labels['pt-BR'])[key]??key;}
export function historyFields(fields,locale){
 if(!Array.isArray(fields)||fields.some(key=>typeof key!=='string'))throw new TypeError('invalid_changed_fields');
 const language=Object.hasOwn(labels,locale)?locale:'pt-BR';
 return [...new Set(fields)].map(key=>({key,label:Object.hasOwn(existing,key)?resourceMessages[language][existing[key]]:historyText(language,Object.hasOwn(basic,key)?basic[key]:'other')}));
}
