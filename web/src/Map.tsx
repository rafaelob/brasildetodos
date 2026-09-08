// SPDX-License-Identifier: AGPL-3.0-or-later
import {useEffect,useRef,useState} from 'react';
import type {Map as LibreMap,GeoJSONSource} from 'maplibre-gl';
import {api} from './api';
import {buildingLayer,cameraOptions,boundaryBbox,validateBoundary,validateCollection,viewportParameters} from './map-policy.mjs';
import {mapText} from './map-text.mjs';
import type {Locale,Place} from './types';
import './map.css';

type Props={locale?:Locale;places:Place[];select:(id:string)=>void;t:(key:string)=>string;onBounds:(bbox:string)=>void;filters?:Record<string,string>};
const EMPTY={type:'FeatureCollection' as const,features:[]};
const reducedMotion=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export default function MapView({select,t,onBounds,filters={},locale='pt-BR'}:Props){
  const [enabled,setEnabled]=useState(false),[attempt,setAttempt]=useState(0);
  const [failed,setFailed]=useState(false),[tileWarning,setTileWarning]=useState(false),[dataFailed,setDataFailed]=useState(false);
  const [ready,setReady]=useState(false),[loadingData,setLoadingData]=useState(false),[hasBuildings,setHasBuildings]=useState(false);
  const [threeD,setThreeD]=useState(false),[matched,setMatched]=useState<number|null>(null);
  const host=useRef<HTMLDivElement>(null),map=useRef<LibreMap|null>(null);
  const selectRef=useRef(select),filtersRef=useRef(filters),refreshRef=useRef<()=>void>(()=>{});
  selectRef.current=select;filtersRef.current=filters;
  const filterKey=JSON.stringify(filters);
  const text=(key:string)=>mapText(locale,key);

  useEffect(()=>{
    if(!enabled||!host.current)return;
    let cancelled=false,loaded=false,broken=false,generation=0,instance:LibreMap|null=null;
    let timer:ReturnType<typeof setTimeout>|undefined,deadline:ReturnType<typeof setTimeout>|undefined;
    let controller:AbortController|undefined;
    setReady(false);setFailed(false);setTileWarning(false);setDataFailed(false);setMatched(null);
    setHasBuildings(false);setThreeD(false);setLoadingData(false);
    function discardPoints(){
      if(cancelled)return;
      (instance?.getSource('bdt-places') as GeoJSONSource|undefined)?.setData(EMPTY);
      setMatched(null);
    }
    function requestData(){
      if(cancelled||broken)return;
      // Invalidate immediately, including during debounce, not after the next fetch.
      generation++;const version=generation;
      clearTimeout(timer);controller?.abort();discardPoints();setDataFailed(false);
      if(!instance||!loaded)return;
      setLoadingData(true);
      timer=setTimeout(async()=>{
        if(cancelled||version!==generation||!instance)return;
        const bounds=instance.getBounds();
        const query=viewportParameters([bounds.getWest(),bounds.getSouth(),bounds.getEast(),bounds.getNorth()],instance.getZoom(),filtersRef.current);
        if(query===null){setLoadingData(false);setDataFailed(true);return;}
        controller=new AbortController();
        try{
          const raw=await api<unknown>('/map/viewport?'+query,{signal:controller.signal});
          if(cancelled||version!==generation)return;
          const collection=validateCollection(raw);
          (instance.getSource('bdt-places') as GeoJSONSource|undefined)?.setData(collection);
          setMatched(collection.matched_records);setDataFailed(false);
        }catch{
          if(!cancelled&&version===generation){discardPoints();setDataFailed(true);}
        }finally{if(!cancelled&&version===generation)setLoadingData(false);}
      },200);
    }
    function fatal(){
      if(cancelled)return;
      broken=true;loaded=false;generation++;controller?.abort();clearTimeout(timer);clearTimeout(deadline);
      setFailed(true);setReady(false);setLoadingData(false);setMatched(null);
    }
    async function start(){
      try{
        const {default:lib}=await import('./map-runtime');
        if(cancelled||!host.current)return;
        instance=new lib.Map({container:host.current,style:'https://tiles.openfreemap.org/styles/liberty',
          center:[-51,-15],zoom:3.2,renderWorldCopies:false,attributionControl:false});
        map.current=instance;
        instance.addControl(new lib.NavigationControl(),'top-right');
        instance.addControl(new lib.AttributionControl({compact:true}),'bottom-right');
        refreshRef.current=requestData;
        deadline=setTimeout(fatal,20000);
        instance.on('error',()=>{if(!cancelled)setTileWarning(true);});
        instance.on('load',()=>{
          if(cancelled||broken||!instance)return;
          clearTimeout(deadline);
          try{
            instance.addSource('bdt-boundary',{type:'geojson',data:EMPTY});
            instance.addLayer({id:'bdt-boundary-fill',type:'fill',source:'bdt-boundary',
              paint:{'fill-color':'#176b55','fill-opacity':.08}});
            instance.addLayer({id:'bdt-boundary-line',type:'line',source:'bdt-boundary',
              paint:{'line-color':'#176b55','line-width':2,'line-dasharray':[2,2]}});
            instance.addSource('bdt-places',{type:'geojson',data:EMPTY});
            instance.addLayer({id:'bdt-groups',type:'circle',source:'bdt-places',filter:['==',['get','cluster'],true],
              paint:{'circle-color':'#176b55','circle-radius':['step',['get','count'],17,100,23,1000,30],'circle-stroke-color':'#ffffff','circle-stroke-width':2}});
            instance.addLayer({id:'bdt-counts',type:'symbol',source:'bdt-places',filter:['==',['get','cluster'],true],
              layout:{'text-field':['to-string',['get','count']],'text-size':12},paint:{'text-color':'#ffffff'}});
            instance.addLayer({id:'bdt-single',type:'circle',source:'bdt-places',filter:['==',['get','cluster'],false],
              paint:{'circle-color':['match',['get','kind'],'school','#b66d26','health','#267790','#176b55'],
                'circle-radius':7,'circle-stroke-color':'#ffffff','circle-stroke-width':2}});
            instance.on('click','bdt-single',event=>{
              const identity=event.features?.[0]?.properties?.id;
              if(typeof identity==='string')selectRef.current(identity);
            });
            instance.on('click','bdt-groups',event=>{
              const props=event.features?.[0]?.properties;
              if(!props||!instance)return;
              const w=Number(props.west),s=Number(props.south),e=Number(props.east),n=Number(props.north);
              if(![w,s,e,n].every(Number.isFinite))return;
              instance.fitBounds([[Math.max(-180,w-.0001),Math.max(-90,s-.0001)],
                [Math.min(180,e+.0001),Math.min(90,n+.0001)]],
                {padding:40,maxZoom:Math.min(20,instance.getZoom()+3),duration:reducedMotion()?0:300});
            });
            for(const layer of ['bdt-single','bdt-groups']){
              instance.on('mouseenter',layer,()=>{if(instance)instance.getCanvas().style.cursor='pointer';});
              instance.on('mouseleave',layer,()=>{if(instance)instance.getCanvas().style.cursor='';});
            }
            const style=instance.getStyle(),buildings=buildingLayer(style);
            if(buildings){
              const before=style.layers.find(layer=>layer.type==='symbol')?.id;
              instance.addLayer(buildings,before);setHasBuildings(true);
            }
            instance.on('moveend',requestData);loaded=true;setReady(true);requestData();
          }catch{fatal();}
        });
      }catch{fatal();}
    }
    void start();
    return()=>{
      cancelled=true;generation++;clearTimeout(timer);clearTimeout(deadline);controller?.abort();
      refreshRef.current=()=>{};instance?.remove();if(map.current===instance)map.current=null;
    };
  },[enabled,attempt]);
  useEffect(()=>{refreshRef.current();},[filterKey]);
  useEffect(()=>{
    const instance=map.current;if(!instance||!ready||!hasBuildings)return;
    if(instance.getLayer('bdt-buildings'))instance.setLayoutProperty('bdt-buildings','visibility',threeD?'visible':'none');
    instance.easeTo(cameraOptions(threeD,reducedMotion()));
  },[threeD,ready,hasBuildings]);
  const activeMunicipality=filters.municipality_id||'';
  useEffect(()=>{
    const instance=map.current;if(!instance||!ready)return;
    const boundarySource=instance.getSource('bdt-boundary') as GeoJSONSource|undefined;
    if(!boundarySource)return;
    if(!activeMunicipality){boundarySource.setData(EMPTY);return;}
    let cancelled=false;
    api<unknown>('/territories/'+encodeURIComponent(activeMunicipality)+'/geometry')
      .then(raw=>{
        if(cancelled)return;
        const valid=validateBoundary(raw);
        if(valid){
          boundarySource.setData(valid as any);
          const box=boundaryBbox(valid);
          if(box&&instance){
            instance.fitBounds([[box[0],box[1]],[box[2],box[3]]],{padding:35,maxZoom:14,duration:reducedMotion()?0:400});
          }
        }else boundarySource.setData(EMPTY);
      })
      .catch(()=>{if(!cancelled)boundarySource.setData(EMPTY);});
    return()=>{cancelled=true;};
  },[activeMunicipality,ready]);
  function useArea(){
    const instance=map.current;if(!instance)return;
    const bounds=instance.getBounds();
    const query=viewportParameters([bounds.getWest(),bounds.getSouth(),bounds.getEast(),bounds.getNorth()],instance.getZoom(),{});
    if(query)onBounds(new URLSearchParams(query).get('bbox')!);
  }
  return <aside className="map-panel" aria-label={t('map')}>
    {!enabled?<div className="map-start"><h2>{t('map')}</h2><p>{t('mapNote')}</p><button className="primary" onClick={()=>setEnabled(true)}>{t('loadMap')}</button></div>:<>
      <div ref={host} className="map-canvas" aria-label={text('canvas')}/>
      <div className="map-actions">
        <button disabled={!ready} onClick={useArea}>{t('mapHere')}</button>
        <button disabled={!ready||!hasBuildings} aria-pressed={threeD} onClick={()=>setThreeD(value=>!value)}>{t('buildings')}</button>
        <button onClick={()=>setEnabled(false)}>{text('hide')}</button>
      </div>
      <div className="map-feedback" aria-live="polite" aria-atomic="true">
        {!ready&&!failed&&<p>{text('loading')}</p>}
        {loadingData&&<p>{text('updating')}</p>}
        {matched!==null&&!loadingData&&<p className="map-caption">{matched.toLocaleString(locale)} {text('count')}</p>}
        {dataFailed&&<p>{t('mapDataFail')} <button onClick={()=>refreshRef.current()}>{t('refresh')}</button></p>}
        {failed&&<p className="callout">{text('styleFailure')}</p>}
        {tileWarning&&!failed&&<p className="callout">{text('tileWarning')}</p>}
        {(failed||tileWarning)&&<button onClick={()=>setAttempt(value=>value+1)}>{text('retry')}</button>}
      </div>
      <div className="map-notes"><small>{t('mapNote')}</small>
        {ready&&!hasBuildings&&<small>{text('unavailable3D')}</small>}
        {threeD&&<><small>{text('zoom3D')}</small><small>{text('geometry3D')}</small></>}
      </div>
    </>}
  </aside>;
}
