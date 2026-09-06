// SPDX-License-Identifier: AGPL-3.0-or-later
export const FAVORITES_KEY='bdt:favorites';
export const WATCH_PAGE_SIZE=12;
export const isPlaceId=value=>typeof value==='string'&&value.length<=180&&/^[a-z0-9_-]+:[A-Za-z0-9._/-]+$/.test(value);

/** Keep valid legacy favorites, preserving order; never send the whole list. */
export function favoriteIds(value){
  return Array.isArray(value)?[...new Set(value.filter(isPlaceId))]:[];
}
export function readFavorites(storage){
  try{return favoriteIds(JSON.parse(storage.getItem(FAVORITES_KEY)||'[]'));}
  catch{return [];}
}
export function saveFavorites(storage,value){
  try{storage.setItem(FAVORITES_KEY,JSON.stringify(favoriteIds(value)));return true;}
  catch{return false;}
}
export function watchPage(value,page=1){
  const ids=favoriteIds(value),pages=Math.max(1,Math.ceil(ids.length/WATCH_PAGE_SIZE));
  const selected=Number.isSafeInteger(page)?Math.max(1,Math.min(page,pages)):1;
  return {ids:ids.slice((selected-1)*WATCH_PAGE_SIZE,selected*WATCH_PAGE_SIZE),page:selected,pages,total:ids.length};
}
export function watchValue(value,locale,t){
  if(value===null||value===undefined||value==='')return t('unknown');
  if(typeof value==='boolean')return t(value?'watchYes':'watchNo');
  if(Array.isArray(value))return value.length?value.map(item=>typeof item==='string'?t(item):t('unknown')).join(' · '):t('unknown');
  if(typeof value==='number')return Number.isFinite(value)?new Intl.NumberFormat(locale,{maximumFractionDigits:7}).format(value):t('unknown');
  return typeof value==='string'?value:t('unknown');
}
export function watchDate(value,locale,t){
  if(typeof value!=='string'||!/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value))return t('unknown');
  const date=new Date(value);return Number.isNaN(date.getTime())?t('unknown'):date.toLocaleString(locale);
}
