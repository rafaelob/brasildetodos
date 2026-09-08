// SPDX-License-Identifier: AGPL-3.0-or-later
import {useEffect,useRef,useState} from 'react';
import type {Map as LibreMap,GeoJSONSource} from 'maplibre-gl';
import {api} from './api';
import {buildingLayer,cameraOptions,boundaryBbox,validateBoundary,validateCollection,viewportParameters} from './map-policy.mjs';
import {mapText} from './map-text.mjs';
import type {Locale,Place} from './types';
import './map.css';

type Props={locale?:Locale;places:Place[];select:(id:string)=>void;t:(key:string)=>string;onBounds:(bbox:string)=>void;filters?:Record<string,string>;focusCoordinates?:[number,number]|null};
const EMPTY={type:'FeatureCollection' as const,features:[]};
const reducedMotion=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;

type CityPreset={id:string;nameKey:string;center:[number,number];zoom:number;pitch:number;bearing:number};
const CITY_PRESETS:CityPreset[]=[
  {id:'brasilia',nameKey:'brasilia3D',center:[-47.8645,-15.7997],zoom:16,pitch:60,bearing:-30},
  {id:'saopaulo',nameKey:'saopaulo3D',center:[-46.6565,-23.5614],zoom:16.5,pitch:60,bearing:45},
  {id:'riodejaneiro',nameKey:'rio3D',center:[-43.1764,-22.9068],zoom:16.2,pitch:60,bearing:25},
  {id:'curitiba',nameKey:'curitiba3D',center:[-49.2667,-25.4167],zoom:16.2,pitch:60,bearing:-20},
  {id:'belohorizonte',nameKey:'belohorizonte3D',center:[-43.9378,-19.9328],zoom:16.2,pitch:60,bearing:15},
  {id:'salvador',nameKey:'salvador3D',center:[-38.5108,-12.9714],zoom:16.2,pitch:60,bearing:-35},
  {id:'recife',nameKey:'recife3D',center:[-34.8711,-8.0631],zoom:16.2,pitch:60,bearing:40},
  {id:'portoalegre',nameKey:'portoalegre3D',center:[-51.2300,-30.0330],zoom:16.2,pitch:60,bearing:-15},
];

export default function MapView({select,t,onBounds,filters={},locale='pt-BR',focusCoordinates=null}:Props){
  const [enabled,setEnabled]=useState(true),[attempt,setAttempt]=useState(0);
  const [failed,setFailed]=useState(false),[tileWarning,setTileWarning]=useState(false),[dataFailed,setDataFailed]=useState(false);
  const [ready,setReady]=useState(false),[loadingData,setLoadingData]=useState(false),[hasBuildings,setHasBuildings]=useState(false);
  const [threeD,setThreeD]=useState(false),[matched,setMatched]=useState<number|null>(null);
  const [cameraPitch,setCameraPitch]=useState(0),[cameraBearing,setCameraBearing]=useState(0),[cameraZoom,setCameraZoom]=useState(3.2);
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
        instance.addControl(new lib.NavigationControl({visualizePitch:true}),'bottom-right');
        instance.addControl(new lib.AttributionControl({compact:true}),'bottom-right');
        refreshRef.current=requestData;
        deadline=setTimeout(fatal,20000);

        const canvas=instance.getCanvas();
        const onLost=(e:Event)=>{
          e.preventDefault();
          if(!cancelled)setTileWarning(true);
        };
        const onRestored=()=>{
          if(!cancelled)setAttempt(a=>a+1);
        };
        canvas.addEventListener('webglcontextlost',onLost);
        canvas.addEventListener('webglcontextrestored',onRestored);

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
              paint:{'circle-color':['match',['get','kind'],'school','#b66d26','health','#267790','work','#9c412b','#176b55'],
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
            const popup=new lib.Popup({closeButton:false,closeOnClick:false,offset:12});
            instance.on('mouseenter','bdt-single',event=>{
              if(!instance)return;
              instance.getCanvas().style.cursor='pointer';
              const f=event.features?.[0],c=(f?.geometry as any)?.coordinates;
              const name=f?.properties?.name||f?.properties?.id,kind=f?.properties?.kind;
              if(c&&name){
                popup.setLngLat(c as [number,number])
                  .setHTML(`<div class="map-popup"><span class="pill ${kind}">${t(kind||'school')}</span><strong>${name}</strong><small>${text('clickToInspect')}</small></div>`)
                  .addTo(instance);
              }
            });
            instance.on('mouseleave','bdt-single',()=>{
              if(instance)instance.getCanvas().style.cursor='';
              popup.remove();
            });
            instance.on('mouseenter','bdt-groups',()=>{if(instance)instance.getCanvas().style.cursor='pointer';});
            instance.on('mouseleave','bdt-groups',()=>{if(instance)instance.getCanvas().style.cursor='';});
            if(instance.getLayer('building-3d')){
              instance.removeLayer('building-3d');
            }
            const style=instance.getStyle(),buildings=buildingLayer(style);
            if(buildings){
              const before=style.layers?.find(layer=>layer.type==='symbol')?.id;
              instance.addLayer(buildings,before);setHasBuildings(true);
            }
            const syncCamera=()=>{
              if(!instance)return;
              setCameraPitch(Math.round(instance.getPitch()));
              setCameraBearing(Math.round(instance.getBearing()));
              setCameraZoom(Number(instance.getZoom().toFixed(1)));
            };
            syncCamera();
            instance.on('moveend',()=>{
              syncCamera();
              requestData();
            });
            loaded=true;setReady(true);requestData();
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
    const targetPitch=threeD?55:0;
    const currentPitch=Math.round(instance.getPitch());
    if(currentPitch!==targetPitch){
      if(threeD&&instance.getZoom()<14.5){
        instance.easeTo({zoom:15.5,pitch:55,duration:reducedMotion()?0:400});
      }else{
        instance.easeTo(cameraOptions(threeD,reducedMotion()));
      }
    }
  },[threeD,ready,hasBuildings]);
  useEffect(()=>{
    if(!focusCoordinates||!focusCoordinates.every(Number.isFinite))return;
    if(!enabled){
      setEnabled(true);
      return;
    }
    const instance=map.current;if(!instance||!ready)return;
    if(!threeD)setThreeD(true);
    instance.flyTo({center:focusCoordinates,zoom:16.5,pitch:55,duration:reducedMotion()?0:1000});
  },[focusCoordinates,ready,enabled]);
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
  function tiltCamera(delta:number){
    const instance=map.current;if(!instance)return;
    const next=Math.max(0,Math.min(75,Math.round(instance.getPitch()+delta)));
    if(!threeD&&next>0)setThreeD(true);
    if(threeD&&next===0)setThreeD(false);
    instance.easeTo({pitch:next,duration:reducedMotion()?0:250});
  }
  function rotateCamera(delta:number){
    const instance=map.current;if(!instance)return;
    instance.easeTo({bearing:Math.round(instance.getBearing()+delta),duration:reducedMotion()?0:250});
  }
  function resetCompass(){
    const instance=map.current;if(!instance)return;
    instance.easeTo({bearing:0,pitch:threeD?55:0,duration:reducedMotion()?0:300});
  }
  function zoomFor3D(){
    const instance=map.current;if(!instance)return;
    instance.easeTo({zoom:Math.max(instance.getZoom(),15.5),pitch:55,duration:reducedMotion()?0:400});
  }
  function jumpToCity(city:CityPreset){
    const instance=map.current;if(!instance)return;
    if(!threeD)setThreeD(true);
    instance.flyTo({center:city.center,zoom:city.zoom,pitch:city.pitch,bearing:city.bearing,duration:reducedMotion()?0:1200});
  }
  return <aside className="map-panel" aria-label={t('map')}>
    {!enabled?<div className="map-collapsed-bar"><button className="primary map-reopen-btn" onClick={()=>setEnabled(true)}>🗺️ {t('loadMap')}</button></div>:
    <div className="map-stage">
      <div ref={host} className="map-canvas" aria-label={text('canvas')}/>

      {/* Floating Top Controls */}
      <div className="map-float-top">
        <div className="map-float-left">
          {matched!==null&&<span className="map-pill map-count-pill">📍 {matched.toLocaleString(locale)} {text('count').split(';')[0]}</span>}
          {loadingData&&<span className="map-pill map-loading-pill">⏳ {text('updating')}</span>}
          <button disabled={!ready} className="map-pill-btn map-btn-area" onClick={useArea} title={t('mapHere')}>
            🔍 {t('mapHere')}
          </button>
        </div>
        <div className="map-float-right">
          <button disabled={!ready||!hasBuildings} className={'map-pill-btn map-btn-3d '+(threeD?'active':'')} aria-pressed={threeD} onClick={()=>setThreeD(value=>!value)}>
            {threeD?`◩ ${text('mode3D')}`:`▱ ${text('mode2D')}`}
          </button>
          <div className="map-tilt-pill" role="group" aria-label={text('camera3D')}>
            <button disabled={!ready} onClick={()=>tiltCamera(15)} title={text('tiltUp')} aria-label={text('tiltUp')}>▲</button>
            <button disabled={!ready} onClick={()=>tiltCamera(-15)} title={text('tiltDown')} aria-label={text('tiltDown')}>▼</button>
            <button disabled={!ready} onClick={()=>rotateCamera(-45)} title={text('rotateLeft')} aria-label={text('rotateLeft')}>↺</button>
            <button disabled={!ready} onClick={()=>rotateCamera(45)} title={text('rotateRight')} aria-label={text('rotateRight')}>↻</button>
            <button disabled={!ready} onClick={resetCompass} title={text('resetCompass')} aria-label={text('resetCompass')}>🧭</button>
          </div>
          <button className="map-pill-btn map-btn-close" onClick={()=>setEnabled(false)} title={text('hide')} aria-label={text('hide')}>✕</button>
        </div>
      </div>

      {/* Floating City Landmarks Bar (when 3D is active) */}
      {threeD&&<div className="map-float-landmarks" role="toolbar" aria-label={text('landmarks3D')}>
        <span className="landmarks-title">🏙️ {text('landmarks3D')}:</span>
        <div className="landmarks-scroll">
          {CITY_PRESETS.map(city=>(
            <button key={city.id} className="city-pill-btn" disabled={!ready} onClick={()=>jumpToCity(city)}>
              {text(city.nameKey)}
            </button>
          ))}
        </div>
      </div>}

      {/* Floating Bottom Telemetry & Status */}
      <div className="map-float-bottom">
        <div className="map-telemetry-pill" aria-label={text('camera3D')}>
          <span><strong>{text('pitch')}:</strong> {cameraPitch}°</span>
          <span><strong>{text('bearing')}:</strong> {cameraBearing}°</span>
          <span><strong>{text('zoom')}:</strong> {cameraZoom}</span>
          {threeD&&cameraZoom<14&&<button className="telemetry-action" onClick={zoomFor3D}>{text('zoomIn3D')} ↗</button>}
        </div>
        {(dataFailed||failed||tileWarning)&&<div className="map-float-warning">
          {dataFailed&&<span>{t('mapDataFail')} <button onClick={()=>refreshRef.current()}>{t('refresh')}</button></span>}
          {failed&&<span className="callout">{text('styleFailure')}</span>}
          {tileWarning&&!failed&&<span className="callout">{text('tileWarning')}</span>}
          {(failed||tileWarning)&&<button onClick={()=>setAttempt(value=>value+1)}>{text('retry')}</button>}
        </div>}
      </div>
    </div>}
  </aside>;
}
