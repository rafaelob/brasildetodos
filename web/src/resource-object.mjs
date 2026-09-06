// SPDX-License-Identifier: AGPL-3.0-or-later
/** A visual preview only. The full object is retained in the DOM, API and exports. */
export function objectPresentation(value){
  if(typeof value!=='string')throw new TypeError('invalid_resource_object');
  const characters=Array.from(value);
  return {text:value,characters:characters.length,long:characters.length>240,
    heading:characters.length>240?characters.slice(0,180).join('')+'…':value};
}
const copy={
 'pt-BR':{full:'Ler objeto completo',characters:'caracteres; texto integral preservado'},
 en:{full:'Read the full object',characters:'characters; full text preserved'},
 es:{full:'Leer el objeto completo',characters:'caracteres; texto íntegro conservado'}
};
export function objectText(locale,key){return (copy[locale]||copy['pt-BR'])[key]||key;}
