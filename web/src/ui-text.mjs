import {watchMessages} from './watch-i18n.mjs';
import {actionMessages} from './resource-actions.mjs';
import {resourceMessages} from './resource-i18n.mjs';
import {translate} from './i18n.mjs';
import {featureMessages} from './features-i18n.mjs';
export const additionalMessages={
  'pt-BR':{placeIdentifier:'Identificador do lugar',observationWithdrawn:'Contribuição retirada pelo autor'},
  en:{placeIdentifier:'Place identifier',observationWithdrawn:'Contribution withdrawn by author'},
  es:{placeIdentifier:'Identificador del lugar',observationWithdrawn:'Contribución retirada por el autor'}
};
export function uiText(locale,key){
  const language=['pt-BR','en','es'].includes(locale)?locale:'pt-BR';
  const token=String(key);
  // Place ineligibility and author withdrawal are different states.
  if(token==='withdrawn')return translate(language,token);
  for(const catalog of [watchMessages[language],actionMessages[language],resourceMessages[language],additionalMessages[language],featureMessages[language]]){
    if(Object.hasOwn(catalog,token)&&typeof catalog[token]==='string')return catalog[token];
  }
  const value=translate(language,token);
  return typeof value==='string'?value:token;
}
export {featureMessages};
