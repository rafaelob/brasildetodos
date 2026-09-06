// SPDX-License-Identifier: AGPL-3.0-or-later
import {objectPresentation,objectText} from './resource-object.mjs';
import type {Locale} from './types';
export default function ResourceObject({text,locale}:{text:string;locale:Locale}){
  const item=objectPresentation(text);
  return <div className="resource-object"><h2>{item.heading}</h2>{item.characters<5&&<p className="callout resource-object-short">{objectText(locale,'short')}</p>}{item.long&&<details>
    <summary>{objectText(locale,'full')} · {item.characters.toLocaleString(locale)} {objectText(locale,'characters')}</summary>
    <p className="resource-object-full">{item.text}</p>
  </details>}</div>;
}
