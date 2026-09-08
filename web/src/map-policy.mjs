// SPDX-License-Identifier: AGPL-3.0-or-later
// Shared policies are independent of WebGL, a provider key, and any LLM.
const FILTERS=['q','kind','state','municipality_id'];
/** @param {number[]} bounds @param {number} zoom @param {Record<string,string>} filters */
export function viewportParameters(bounds,zoom,filters={}){
  if(bounds.length!==4||!bounds.every(Number.isFinite)||!Number.isFinite(zoom))return null;
  const [w,s,e,n]=bounds;
  const box=[Math.max(-180,w),Math.max(-90,s),Math.min(180,e),Math.min(90,n)];
  if(box[0]>=box[2]||box[1]>=box[3])return null;
  const query=new URLSearchParams({bbox:box.join(','),zoom:String(Math.max(0,Math.min(20,Math.floor(zoom))))});
  for(const key of FILTERS)if(typeof filters[key]==='string'&&filters[key])query.set(key,filters[key]);
  return query.toString();
}
/** @param {any} style @returns {any | null} */
export function buildingLayer(style){
  const sourceLayer=style?.layers?.find((layer)=>layer['source-layer']==='building'
    && typeof layer.source==='string' && style.sources?.[layer.source]?.type==='vector');
  if(!sourceLayer)return null;
  const height=['to-number',['get','render_height'],0];
  return {id:'bdt-buildings',type:'fill-extrusion',source:sourceLayer.source,'source-layer':'building',
    minzoom:15,layout:{visibility:'none'},
    filter:['all',['has','render_height'],['>',height,0],['<=',height,2000],
      ['!',['in',['to-string',['get','hide_3d']],['literal',['true','1']]]]],
    paint:{'fill-extrusion-color':'#8cb2a5','fill-extrusion-height':height,
      'fill-extrusion-base':['min',height,['max',0,['to-number',['get','render_min_height'],0]]],
      'fill-extrusion-opacity':.85}};
}
/** @param {boolean} threeD @param {boolean} reducedMotion */
export function cameraOptions(threeD,reducedMotion){return {pitch:threeD?55:0,duration:reducedMotion?0:300};}

/** @param {any} collection @returns {any} */
export function validateCollection(collection){
  const fail=()=>{throw new Error('invalid_map_collection');};
  if(!collection||collection.type!=='FeatureCollection'||!Array.isArray(collection.features)
    ||collection.features.length>500||!Number.isSafeInteger(collection.matched_records)
    ||collection.matched_records<0||collection.matched_records!==collection.represented_records)fail();
  let count=0;const seen=new Set();
  for(const feature of collection.features){
    const p=feature?.properties,c=feature?.geometry?.coordinates;
    if(feature?.type!=='Feature'||feature?.geometry?.type!=='Point'||!Array.isArray(c)||c.length!==2
      ||!c.every(Number.isFinite)||Math.abs(c[0])>180||Math.abs(c[1])>90||!p
      ||typeof p.cluster!=='boolean'||!Number.isSafeInteger(p.count)||p.count<1
      ||typeof p.id!=='string'||!p.id||p.id.length>200||seen.has(p.id))fail();
    if(p.cluster){
      if(p.count<2||p.location_kind!=='aggregate_not_facility'
        ||![p.west,p.south,p.east,p.north].every(Number.isFinite)
        ||p.west>p.east||p.south>p.north||p.west< -180||p.east>180||p.south< -90||p.north>90)fail();
    }else if(p.count!==1||!['school','health','work'].includes(p.kind))fail();
    seen.add(p.id);count+=p.count;
  }
  if(!Number.isSafeInteger(count)||count!==collection.matched_records)fail();
  return collection;
}

/** @param {any} geojson @returns {any} */
export function validateBoundary(geojson){
  if(!geojson||typeof geojson!=='object')return null;
  const features=geojson.type==='FeatureCollection'&&Array.isArray(geojson.features)?geojson.features:
    geojson.type==='Feature'?[geojson]:null;
  if(!features||!features.length)return null;
  for(const f of features){
    if(f?.type!=='Feature'||!['Polygon','MultiPolygon'].includes(f?.geometry?.type))return null;
    if(!Array.isArray(f?.geometry?.coordinates)||!f.geometry.coordinates.length)return null;
  }
  return geojson.type==='FeatureCollection'?geojson:{type:'FeatureCollection',features};
}

/** @param {any} geojson @returns {[number, number, number, number] | null} */
export function boundaryBbox(geojson){
  const valid=validateBoundary(geojson);
  if(!valid)return null;
  let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
  /** @param {any} coords */
  function walk(coords){
    if(!Array.isArray(coords))return;
    if(coords.length>=2&&typeof coords[0]==='number'&&typeof coords[1]==='number'){
      const x=coords[0],y=coords[1];
      if(Number.isFinite(x)&&Number.isFinite(y)&&x>=-180&&x<=180&&y>=-90&&y<=90){
        if(x<minX)minX=x;if(x>maxX)maxX=x;
        if(y<minY)minY=y;if(y>maxY)maxY=y;
      }
    }else{
      for(const child of coords)walk(child);
    }
  }
  for(const feature of valid.features){
    walk(feature.geometry.coordinates);
  }
  if(!Number.isFinite(minX)||!Number.isFinite(minY)||!Number.isFinite(maxX)||!Number.isFinite(maxY))return null;
  if(minX>maxX||minY>maxY)return null;
  return [minX,minY,maxX,maxY];
}

