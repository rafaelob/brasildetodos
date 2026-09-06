import {useEffect,useRef,useState} from 'react';
import type {Map as MapType, GeoJSONSource} from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type {Place} from './types';

export default function MapView({places,select,t,onBounds}:{places:Place[]; select:(id:string)=>void; t:(key:string)=>string; onBounds:(bbox:string)=>void}) {
  const holder=useRef<HTMLDivElement>(null), map=useRef<MapType|null>(null), current=useRef(places), selection=useRef(select);
  const [enabled,setEnabled]=useState(false), [failed,setFailed]=useState(false), [ready,setReady]=useState(false), [threeD,setThreeD]=useState(false);
  current.current=places; selection.current=select;
  const geo=(rows:Place[])=>({type:'FeatureCollection' as const, features:rows.filter(p=>p.latitude!==null && p.longitude!==null).map(p=>({type:'Feature' as const, geometry:{type:'Point' as const, coordinates:[p.longitude!,p.latitude!]}, properties:{id:p.id,kind:p.kind,name:p.name}}))});
  useEffect(()=>{
    if(!enabled || !holder.current) return;
    let disposed=false;
    import('maplibre-gl').then(lib=>{
      if(disposed || !holder.current) return;
      let instance:MapType;
      try { instance=new lib.Map({container:holder.current,style:'https://tiles.openfreemap.org/styles/liberty',center:[-51,-15],zoom:3.2,attributionControl:{compact:false}}); }
      catch {setFailed(true);return;}
      map.current=instance;
      instance.addControl(new lib.NavigationControl(),'top-right');
      instance.on('error',()=>{if(!instance.isStyleLoaded())setFailed(true);});
      instance.on('load',()=>{
        if(disposed)return;
        instance.addSource('places',{type:'geojson',data:geo(current.current),cluster:true,clusterRadius:45});
        instance.addLayer({id:'clusters',type:'circle',source:'places',filter:['has','point_count'],paint:{'circle-color':'#125d53','circle-radius':22}});
        instance.addLayer({id:'cluster-count',type:'symbol',source:'places',filter:['has','point_count'],layout:{'text-field':['get','point_count_abbreviated'],'text-size':13},paint:{'text-color':'#fff'}});
        instance.addLayer({id:'places',type:'circle',source:'places',filter:['!', ['has','point_count']],paint:{'circle-color':['match',['get','kind'],'school','#247db2','health','#b35b66','#b57914'],'circle-radius':8,'circle-stroke-color':'#fff','circle-stroke-width':2}});
        instance.on('click','places',e=>{const id=e.features?.[0]?.properties?.id;if(typeof id==='string')selection.current(id);});
        instance.on('click','clusters',async e=>{const feature=e.features?.[0];if(!feature)return;const zoom=await (instance.getSource('places') as GeoJSONSource).getClusterExpansionZoom(feature.properties.cluster_id); if(!disposed&&feature.geometry.type==='Point')instance.easeTo({center:feature.geometry.coordinates as [number,number],zoom});});
        instance.addSource('buildings',{type:'vector',url:'https://tiles.openfreemap.org/planet'});
        instance.addLayer({id:'buildings-3d',type:'fill-extrusion',source:'buildings','source-layer':'building',minzoom:15,filter:['all',['has','render_height'],['>', ['get','render_height'],0],['!=',['get','hide_3d'],true]],layout:{visibility:'none'},paint:{'fill-extrusion-color':'#91aaa1','fill-extrusion-height':['get','render_height'],'fill-extrusion-base':['coalesce',['get','render_min_height'],0],'fill-extrusion-opacity':0.8}});
        setReady(true);setFailed(false);
      });
    }).catch(()=>setFailed(true));
    return()=>{disposed=true;map.current?.remove();map.current=null;setReady(false);};
  },[enabled]);
  useEffect(()=>{if(ready && map.current)(map.current.getSource('places') as GeoJSONSource)?.setData(geo(places));},[places,ready]);
  function toggle(){if(!map.current||!ready)return;const next=!threeD;setThreeD(next);map.current.easeTo({pitch:next?55:0});map.current.setLayoutProperty('buildings-3d','visibility',next?'visible':'none');}
  return <section className="map-panel" aria-label={t('loadMap')}>
    {!enabled?<div className="map-start"><span className="map-grid" aria-hidden="true">◎</span><h2>{t('loadMap')}</h2><p>{t('mapConsent')}</p><button className="primary" onClick={()=>setEnabled(true)}>{t('loadMap')}</button></div>:<>
    <div ref={holder} className="map-canvas"/>
    <div className="map-actions"><button disabled={!ready} aria-pressed={threeD} onClick={toggle}>{t('buildings')}</button><button disabled={!ready} onClick={()=>{const b=map.current?.getBounds();if(b)onBounds([b.getWest(),b.getSouth(),b.getEast(),b.getNorth()].map(v=>v.toFixed(5)).join(','));}}>{t('mapHere')}</button></div>
    {failed&&<p role="status" className="map-error">{t('mapFail')}</p>}
    <p className="map-caption">{threeD?t('buildingsNote'):t('mapNote')}</p></>}
  </section>;
}
