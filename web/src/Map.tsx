import {useEffect,useRef,useState} from 'react';
import type {Map as LibreMap,GeoJSONSource} from 'maplibre-gl';
import {api} from './api';
import type {Place} from './types';

type Feature={type:'Feature';geometry:{type:'Point';coordinates:number[]};properties:Record<string,string|number|boolean>};
type Collection={type:'FeatureCollection';features:Feature[];matched_records:number;represented_records:number};
type Props={places:Place[];select:(id:string)=>void;t:(key:string)=>string;onBounds:(bbox:string)=>void;filters?:Record<string,string>};
const EMPTY={type:'FeatureCollection' as const,features:[]};

export default function MapView({select,t,onBounds,filters={}}:Props){
  const [enabled,setEnabled]=useState(false),[failed,setFailed]=useState(false),[dataFailed,setDataFailed]=useState(false);
  const [ready,setReady]=useState(false),[threeD,setThreeD]=useState(false),[matched,setMatched]=useState<number|null>(null);
  const host=useRef<HTMLDivElement>(null),map=useRef<LibreMap|null>(null);
  const selectRef=useRef(select),filtersRef=useRef(filters),refreshRef=useRef<()=>void>(()=>{});
  selectRef.current=select;filtersRef.current=filters;
  const filterKey=JSON.stringify(filters);
  useEffect(()=>{
    if(!enabled||!host.current)return;
    let cancelled=false,timer:ReturnType<typeof setTimeout>|undefined,controller:AbortController|undefined,generation=0;
    setReady(false);setFailed(false);setDataFailed(false);setMatched(null);
    async function start(){
      try{
        const lib=await import('maplibre-gl');
        await import('maplibre-gl/dist/maplibre-gl.css');
        if(cancelled||!host.current)return;
        const instance=new lib.Map({container:host.current,style:'https://tiles.openfreemap.org/styles/liberty',
          center:[-51,-15],zoom:3.2,renderWorldCopies:false});
        map.current=instance;
        instance.addControl(new lib.NavigationControl(),'top-right');
        instance.addControl(new lib.AttributionControl({compact:true}),'bottom-right');
        const requestData=()=>{
          clearTimeout(timer);
          timer=setTimeout(async()=>{
            if(cancelled)return;
            controller?.abort();controller=new AbortController();const version=++generation;
            const bounds=instance.getBounds();
            const west=Math.max(-180,bounds.getWest()),east=Math.min(180,bounds.getEast());
            const south=Math.max(-90,bounds.getSouth()),north=Math.min(90,bounds.getNorth());
            if(west>=east||south>=north)return;
            const parameters=new URLSearchParams({bbox:[west,south,east,north].join(','),zoom:String(Math.max(0,Math.min(20,Math.floor(instance.getZoom()))))});
            for(const[key,value]of Object.entries(filtersRef.current))if(value)parameters.set(key,value);
            try{
              const collection=await api<Collection>('/map/viewport?'+parameters,{signal:controller.signal});
              if(cancelled||version!==generation)return;
              if(collection.represented_records!==collection.matched_records)throw new Error('map-accounting-mismatch');
              (instance.getSource('bdt-places') as GeoJSONSource|undefined)?.setData(collection);
              setMatched(collection.matched_records);setDataFailed(false);
            }catch(error){if(!cancelled&&version===generation&&!(error instanceof DOMException&&error.name==='AbortError'))setDataFailed(true);}
          },250);
        };
        refreshRef.current=requestData;
        instance.on('error',()=>{if(!cancelled)setFailed(true);});
        instance.on('load',()=>{
          if(cancelled)return;
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
            if(!props)return;
            const w=Number(props.west),s=Number(props.south),e=Number(props.east),n=Number(props.north);
            if(![w,s,e,n].every(Number.isFinite))return;
            instance.fitBounds([[w-.0001,s-.0001],[e+.0001,n+.0001]],{padding:50,maxZoom:Math.min(20,instance.getZoom()+3)});
          });
          for(const layer of ['bdt-single','bdt-groups']){
            instance.on('mouseenter',layer,()=>{instance.getCanvas().style.cursor='pointer';});
            instance.on('mouseleave',layer,()=>{instance.getCanvas().style.cursor='';});
          }
          const vectorSource=Object.entries(instance.getStyle().sources).find(([,value])=>value.type==='vector')?.[0];
          if(vectorSource){
            instance.addLayer({id:'bdt-buildings',source:vectorSource,'source-layer':'building',type:'fill-extrusion',minzoom:15,
              layout:{visibility:'none'},filter:['all',['has','render_height'],['>',['get','render_height'],0]],
              paint:{'fill-extrusion-color':'#aac5bd','fill-extrusion-height':['get','render_height'],
                'fill-extrusion-base':['coalesce',['get','render_min_height'],0],'fill-extrusion-opacity':.65}});
          }
          instance.on('moveend',requestData);setReady(true);requestData();
        });
      }catch{if(!cancelled)setFailed(true);}
    }
    start();
    return()=>{cancelled=true;generation++;clearTimeout(timer);controller?.abort();refreshRef.current=()=>{};map.current?.remove();map.current=null;};
  },[enabled]);
  useEffect(()=>{if(map.current){map.current.jumpTo({center:[-51,-15],zoom:3.2});refreshRef.current();}},[filterKey]);
  useEffect(()=>{
    const instance=map.current;if(!instance||!ready)return;
    if(instance.getLayer('bdt-buildings'))instance.setLayoutProperty('bdt-buildings','visibility',threeD?'visible':'none');
    instance.easeTo({pitch:threeD?55:0,duration:300});
  },[threeD,ready]);
  return <aside className="map-panel" aria-label={t('map')}>
    {!enabled?<div className="map-start"><h2>{t('map')}</h2><p>{t('mapNote')}</p><button className="primary" onClick={()=>setEnabled(true)}>{t('loadMap')}</button></div>:<>
      <div ref={host} className="map-canvas"/>
      <div className="map-actions"><button disabled={!ready} onClick={()=>{const b=map.current?.getBounds();if(b)onBounds([Math.max(-180,b.getWest()),Math.max(-90,b.getSouth()),Math.min(180,b.getEast()),Math.min(90,b.getNorth())].join(','));}}>{t('mapHere')}</button>
        <button disabled={!ready} aria-pressed={threeD} onClick={()=>setThreeD(value=>!value)}>{t('buildings')}</button></div>
      {matched!==null&&<p className="map-caption" role="status">{matched.toLocaleString()} {t('mapRecords')}</p>}
      {dataFailed&&<p role="status">{t('mapDataFail')} <button onClick={()=>refreshRef.current()}>{t('refresh')}</button></p>}
      {failed&&<p className="callout">{t('mapFail')}</p>}
      <small>{t('mapNote')}</small>{threeD&&<small>{t('buildingsNote')}</small>}
    </>}
  </aside>;
}
