// SPDX-License-Identifier: AGPL-3.0-or-later
// Client-authored drafting aid. The unmodified observation API stores this as
// citizen text, not as an official checklist or a server-verified source snapshot.
import {visitText} from './visit-text.mjs';
import {formatDataset} from './i18n.mjs';
const questions={
 identification:['Há nome ou identificação legível na fachada?','Is a name or identification readable on the facade?','¿Hay un nombre o identificación legible en la fachada?'],
 posted_hours:['Há um aviso de horário legível na entrada?','Is a notice of opening hours readable at the entrance?','¿Hay un aviso de horario legible en la entrada?'],
 entrance_barrier:['Você observou alguma barreira física na entrada?','Did you observe a physical barrier at the entrance?','¿Observó alguna barrera física en la entrada?'],
 works_visible:['Há sinal visível de obra ou reforma no local?','Is there a visible sign of construction or renovation at the site?','¿Hay señales visibles de obra o reforma en el lugar?'],
 health_sign:['Há uma identificação visível dos serviços de saúde oferecidos?','Is there a visible notice identifying the health services offered?','¿Hay un aviso visible que identifica los servicios de salud ofrecidos?'],
 project_notice:['Há placa legível identificando a obra?','Is there a readable sign identifying the construction project?','¿Hay un cartel legible que identifica la obra?'],
 perimeter:['Há sinalização ou delimitação visível do canteiro?','Is there visible signage or a boundary around the construction site?','¿Hay señalización o delimitación visible de la obra?'],
 pedestrian_passage:['Você observou uma passagem de pedestres no entorno?','Did you observe a pedestrian passage around the site?','¿Observó un paso peatonal alrededor del lugar?'],
};
const kinds={school:['identification','posted_hours','entrance_barrier','works_visible'],health:['identification','posted_hours','entrance_barrier','health_sign'],work:['project_notice','perimeter','pedestrian_passage','works_visible']};
export const MAX_BODY=1200;
export function visitGuide(kind,locale) {
 const index=['pt-BR','en','es'].indexOf(locale);
 if(index<0||!Object.hasOwn(kinds,kind))throw new Error('unsupported_guide');
 return {id:`bdt.${kind}.field.v1`,locale,kind,items:kinds[kind].map(id=>({id,label:questions[id][index],allowed_answers:['yes','no','unknown']}))};
}
export function composeVisit(place,locale,answers,note) {
 const guide=visitGuide(place.kind,locale),words=visitText[locale];
 if(typeof note!=='string'||Array.from(note.trim()).length<20)throw new Error('context_required');
 if(Object.keys(answers).length!==guide.items.length||guide.items.some(i=>!i.allowed_answers.includes(answers[i.id])))throw new Error('answers_incomplete');
 const rawStr = typeof place.source?.reference_date === 'string' ? place.source.reference_date.trim() : '';
 const lower = rawStr.toLowerCase();
 const isMissing = !rawStr || ['não informado', 'nao informado', 'no informado', 'not provided', 'unknown', 'null', 'undefined', 'none'].includes(lower);
 const ref = isMissing ? words.missing : rawStr;
 const body=[`${words.open} · ${guide.id} · ${locale}`,`${words.context}: ${place.id}`,`${words.source}: ${formatDataset(place.source?.dataset,locale)||'—'} · ${ref}`,
  '',...guide.items.map(i=>`${i.label} ${words[answers[i.id]]}`),'',`${words.note}: ${note.trim()}`].join('\n');
 if(Array.from(body).length>MAX_BODY)throw new Error('observation_budget');
 return body;
}
export function publicObservationReport(row,locale) {
 if(row.status!=='approved'||!Object.hasOwn(visitText,locale))throw new Error('observation_not_public');
 const raw=row.observation;
 if(!raw||typeof raw.body!=='string'||Array.from(raw.body).length>MAX_BODY)throw new Error('invalid_public_observation');
 return {schema:'bdt.citizen-observation-copy.v1',locale,id:row.id,place_id:row.place_id,
  created_at:row.created_at,reviewed_at:row.reviewed_at,
  notice:visitText[locale].publicNotice,
  observation:Object.fromEntries(['mode','observed_on','body','reference_url'].map(k=>[k,raw[k]??null]))};
}
