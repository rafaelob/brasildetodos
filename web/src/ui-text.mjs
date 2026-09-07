import {regionMessages} from './region-text.mjs';
import {coverageMessages} from './coverage-text.mjs';
import {watchMessages} from './watch-i18n.mjs';
import {actionMessages} from './resource-actions.mjs';
import {resourceMessages} from './resource-i18n.mjs';
import {translate} from './i18n.mjs';
import {featureMessages} from './features-i18n.mjs';
export const additionalMessages={
  'pt-BR':{loadingPlace:'Abrindo a ficha do lugar…',cancelPlace:'Cancelar abertura da ficha',groups:'Grupos',placeIdentifier:'Identificador do lugar',observationWithdrawn:'Contribuição retirada pelo autor'},
  en:{loadingPlace:'Opening place details…',cancelPlace:'Cancel opening place',groups:'Groups',placeIdentifier:'Place identifier',observationWithdrawn:'Contribution withdrawn by author'},
  es:{loadingPlace:'Abriendo la ficha del lugar…',cancelPlace:'Cancelar apertura de ficha',groups:'Grupos',placeIdentifier:'Identificador del lugar',observationWithdrawn:'Contribución retirada por el autor'}
};
export function uiText(locale,key){
  const language=['pt-BR','en','es'].includes(locale)?locale:'pt-BR';
  const token=String(key);
  // Place ineligibility and author withdrawal are different states.
  if(token==='withdrawn')return translate(language,token);
  for(const catalog of [regionMessages[language],coverageMessages[language],watchMessages[language],actionMessages[language],resourceMessages[language],additionalMessages[language],featureMessages[language]]){
    if(Object.hasOwn(catalog,token)&&typeof catalog[token]==='string')return catalog[token];
  }
  const value=translate(language,token);
  return typeof value==='string'?value:token;
}
export {featureMessages};
