// SPDX-License-Identifier: AGPL-3.0-or-later
/** A visual preview only. The full object is retained in the DOM, API and exports. */
export function objectPresentation(value){
  if(typeof value!=='string')throw new TypeError('invalid_resource_object');
  const characters=Array.from(value);
  return {text:value,characters:characters.length,long:characters.length>240,
    heading:characters.length>240?characters.slice(0,180).join('')+'…':value};
}
const copy={
 'pt-BR':{short:'A descrição do objeto na fonte é muito curta. Consulte o registro original.',full:'Ler objeto completo',characters:'caracteres; texto integral preservado'},
 en:{short:'The source object description is very short. Check the original record.',full:'Read the full object',characters:'characters; full text preserved'},
 es:{short:'La descripción del objeto en la fuente es muy breve. Consulte el registro original.',full:'Leer el objeto completo',characters:'caracteres; texto íntegro conservado'}
};
export function objectText(locale,key){return (copy[locale]||copy['pt-BR'])[key]||key;}
