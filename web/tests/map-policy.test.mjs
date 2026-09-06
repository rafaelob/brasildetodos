import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {viewportParameters, buildingLayer, validateCollection, cameraOptions} from '../src/map-policy.mjs';
import {mapText, MAP_TEXT} from '../src/map-text.mjs';

const one = () => ({type:'FeatureCollection',matched_records:1,represented_records:1,features:[{
  type:'Feature',geometry:{type:'Point',coordinates:[-51,-15]},
  properties:{id:'test:point',kind:'school',count:1,cluster:false},
}]});
const style = () => ({version:8,sources:{wrong:{type:'vector'},right:{type:'vector'}},layers:[
  {id:'water',type:'fill',source:'wrong','source-layer':'water'},
  {id:'buildings',type:'fill',source:'right','source-layer':'building'},
]});

test('worker is bundled by Vite, loaded only by the optional map runtime',()=>{
  const runtime=readFileSync(new URL('../src/map-runtime.ts',import.meta.url),'utf8');
  assert.ok(runtime.includes('maplibre-gl-worker.mjs?worker&url'));
  assert.ok(runtime.includes('setWorkerUrl(workerUrl)'));
  const component=readFileSync(new URL('../src/Map.tsx',import.meta.url),'utf8');
  assert.ok(component.includes("await import('./map-runtime')"));
});
test('viewport clamps projection and ignores parameters not present in the public filter contract',()=>{
  const query=new URLSearchParams(viewportParameters([-190,-100,190,100],21.8,{q:'100% saúde',state:'BA',bbox:'override',zoom:'99',secret:'ignored'}));
  assert.equal(query.get('bbox'),'-180,-90,180,90');assert.equal(query.get('zoom'),'20');
  assert.equal(query.get('q'),'100% saúde');assert.equal(query.get('secret'),null);
});
for(const bounds of [[1,2,1,3],[1,3,2,2],[NaN,0,1,2],[0,0,Infinity,1],[0,0,1]]){
  test('invalid viewport has no query: '+String(bounds),()=>assert.equal(viewportParameters(bounds,2,{}),null));
}
test('non-finite zoom has no query',()=>assert.equal(viewportParameters([-60,-30,-30,0],NaN,{}),null));
test('building layer uses the explicitly declared building source, not the first vector',()=>{
  const layer=buildingLayer(style());assert.equal(layer.source,'right');assert.equal(layer['source-layer'],'building');
  assert.equal(layer.minzoom,15);assert.equal(layer.layout.visibility,'none');
  assert.ok(JSON.stringify(layer.filter).includes('hide_3d'));
  assert.ok(JSON.stringify(layer.filter).includes('render_height'));
});
test('no compatible source means no claimed building layer',()=>{
  assert.equal(buildingLayer({sources:{foo:{type:'vector'}},layers:[]}),null);
  const data=style();data.sources.right.type='raster';assert.equal(buildingLayer(data),null);
  assert.equal(buildingLayer(null),null);
});
test('camera follows reduced-motion preference without changing selected perspective',()=>{
  assert.deepEqual(cameraOptions(true,true),{pitch:55,duration:0});
  assert.deepEqual(cameraOptions(false,false),{pitch:0,duration:300});
});
test('valid collection and explicit empty collection retain accounting',()=>{
  assert.equal(validateCollection(one()).matched_records,1);
  assert.equal(validateCollection({type:'FeatureCollection',features:[],matched_records:0,represented_records:0}).matched_records,0);
});
test('aggregate is not a facility and accounts for every represented record',()=>{
  const data=one();data.matched_records=data.represented_records=200;
  data.features[0].properties={id:'grid:1:2:3',count:200,cluster:true,location_kind:'aggregate_not_facility',west:-52,south:-16,east:-50,north:-14};
  assert.equal(validateCollection(data).features[0].properties.count,200);
});
const corruptions = {
  mismatched_total:d=>d.represented_records=2,
  false_feature_sum:d=>d.matched_records=d.represented_records=2,
  negative_count:d=>d.features[0].properties.count=-1,
  missing_cluster:d=>delete d.features[0].properties.cluster,
  imprecise_total:d=>d.matched_records=2**54,
  invented_single:d=>delete d.features[0].properties.id,
  unsupported_kind:d=>d.features[0].properties.kind='imagined',
  outside_world:d=>d.features[0].geometry.coordinates[0]=181,
  invalid_number:d=>d.features[0].geometry.coordinates[1]=NaN,
  invalid_shape:d=>d.features[0].geometry.type='Polygon',
  duplicate:d=>{d.features.push(structuredClone(d.features[0]));d.matched_records=d.represented_records=2;},
  too_many:d=>{d.features=Array(501).fill(d.features[0]);d.matched_records=d.represented_records=501;},
  unlabeled_aggregate:d=>{d.features[0].properties.cluster=true;d.features[0].properties.count=2;d.matched_records=d.represented_records=2;},
};
for(const [name,change] of Object.entries(corruptions))test('reject invalid map payload: '+name,()=>{
  const value=one();change(value);assert.throws(()=>validateCollection(value),/invalid_map_collection/);
});
test('all map messages exist in three languages and fallback is explicit',()=>{
  const keys=Object.keys(MAP_TEXT['pt-BR']).sort();
  for(const lang of ['pt-BR','en','es']){
    assert.deepEqual(Object.keys(MAP_TEXT[lang]).sort(),keys);
    for(const key of keys)assert.ok(mapText(lang,key).length>0);
  }
  assert.equal(mapText('fr','retry'),mapText('pt-BR','retry'));
});
