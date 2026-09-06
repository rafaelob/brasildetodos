import {translate} from './i18n.mjs';
import {featureMessages,featureText} from './features-i18n.mjs';
export const additionalMessages={
  'pt-BR':{placeIdentifier:'Identificador do lugar',observationWithdrawn:'Contribuição retirada pelo autor'},
  en:{placeIdentifier:'Place identifier',observationWithdrawn:'Contribution withdrawn by author'},
  es:{placeIdentifier:'Identificador del lugar',observationWithdrawn:'Contribución retirada por el autor'}
};
export function uiText(locale,key){
  const language=['pt-BR','en','es'].includes(locale)?locale:'pt-BR';
  // The existing withdrawn key refers to a place no longer eligible in a source,
  // not a citizen withdrawing an observation. Keep those meanings distinct.
  if(key==='withdrawn')return translate(language,key);
  return additionalMessages[language]?.[key]??featureText(language,key)??translate(language,key);
}
export {featureMessages};
