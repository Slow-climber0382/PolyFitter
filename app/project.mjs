import {MAX_FACES, inspectMesh} from './geometry.mjs';
import {BODY_TYPES,DEFAULT_STATURE,DETAILS,LIMB_FIELDS} from './avatar.mjs';

export const REGIONS = {
  head:{label:'Głowa',part:'Hełm',size:[158,222,190],gap:5},
  chest:{label:'Klatka piersiowa',part:'Napierśnik',size:[350,550,230],gap:8},
  shin:{label:'Goleń',part:'Ochraniacz goleni',size:[105,395,115],gap:5}
};
export const SHIN_STYLES = {front:'Płyta z przodu',wrap:'Wokół nogi'};
export const DEFAULT_SHIN_STYLE = 'wrap';
export const MAX_PROJECT_BYTES=150_000_000;
export const MAX_PROJECT_FACES=2000000;
export const freshProfile=()=>({
  avatar:{type:'neutral',stature:DEFAULT_STATURE},
  ...Object.fromEntries(Object.entries(REGIONS).map(([key,r])=>[key,{dimensions:[...r.size],gap:r.gap,details:{}}]))
});
const valid=(n,min,max)=>typeof n==='number'&&Number.isFinite(n)&&n>=min&&n<=max;
const triple=(items,min,max)=>Array.isArray(items)&&items.length===3&&items.every(n=>valid(n,min,max));
const fail=()=>{throw Error('Nieprawidłowy lub nieobsługiwany projekt PolyFitter.');};
export function packProject(profile,parts,active) {
  const data={version:1,profile,active,parts:parts.map(part=>({
    name:part.name,region:part.region,transform:part.transform,...(part.group?{group:part.group}:{}),
    ...(part.region==='shin'?{shinStyle:part.shinStyle??DEFAULT_SHIN_STYLE,shinSide:part.shinSide??'L'}:{}),
    // Store original centered vertices. Never bake transforms into a project save.
    vertices:encodeFloats(part.mesh)
  }))};
  return new TextEncoder().encode(JSON.stringify(data)).buffer;
}
function encodeFloats(mesh){
  const buffer=new Uint8Array(mesh.length*4), view=new DataView(buffer.buffer);
  mesh.forEach((n,i)=>view.setFloat32(i*4,n,true));
  let binary='';
  for(let i=0;i<buffer.length;i+=16384)binary+=String.fromCharCode(...buffer.subarray(i,i+16384));
  return btoa(binary);
}
function decodeFloats(encoded){
  if(typeof encoded!=='string'||encoded.length>MAX_FACES*48)fail();
  const binary=atob(encoded);
  if(!binary.length||binary.length%36||binary.length/36>MAX_FACES)fail();
  const buffer=Uint8Array.from(binary,c=>c.charCodeAt(0)), view=new DataView(buffer.buffer);
  const mesh=new Float32Array(buffer.length/4);
  for(let i=0;i<mesh.length;i++){
    const n=view.getFloat32(i*4,true);
    if(!valid(n,-1e7,1e7))fail();mesh[i]=n;
  }
  return mesh;
}
export function openProject(text){
  let value;
  try{value=JSON.parse(text);}catch{fail();}
  if(value?.version!==1||!Array.isArray(value.parts)||value.parts.length>100||!value.profile)fail();
  const profile=freshProfile();
  if(value.profile.avatar!==undefined){
    const {type,stature}=value.profile.avatar??{};
    if(typeof type!=='string'||!Object.hasOwn(BODY_TYPES,type)||!valid(stature,800,2500))fail();
    profile.avatar={type,stature};
    if(value.profile.avatar.headMeasured!==undefined){if(typeof value.profile.avatar.headMeasured!=='boolean')fail();profile.avatar.headMeasured=value.profile.avatar.headMeasured;}
    if(value.profile.avatar.locks!==undefined){
      const locks=value.profile.avatar.locks;
      if(!locks||typeof locks!=='object'||Array.isArray(locks)||Object.keys(locks).length>150)fail();
      profile.avatar.locks={};for(const [key,v] of Object.entries(locks)){if(!/^(head|chest|arm[LR]|leg[LR])\.[A-Za-z]+$/.test(key)||typeof v!=='boolean')fail();profile.avatar.locks[key]=v;}
    }
    if(value.profile.avatar.shapes!==undefined){
      const shapes=value.profile.avatar.shapes;if(!shapes||typeof shapes!=='object'||Array.isArray(shapes))fail();
      profile.avatar.shapes={};
      for(const [group,fields] of Object.entries(shapes)){
        if(!['head','chest','armR','armL','legR','legL'].includes(group)||!fields||typeof fields!=='object'||Array.isArray(fields))fail();
        profile.avatar.shapes[group]={};
        for(const [key,v] of Object.entries(fields)){if(!/^[A-Za-z]+$/.test(key)||!valid(v,60,160))fail();profile.avatar.shapes[group][key]=v;}
      }
    }
    if(value.profile.avatar.limbs!==undefined){
      const limbs=value.profile.avatar.limbs;
      if(!limbs||typeof limbs!=='object'||Array.isArray(limbs))fail();
      profile.avatar.limbs={};
      for(const group of ['armL','armR','legL','legR']){
        if(limbs[group]===undefined)continue;
        if(!limbs[group]||typeof limbs[group]!=='object'||Array.isArray(limbs[group]))fail();
        profile.avatar.limbs[group]={};
        for(const [key,amount] of Object.entries(limbs[group])){
          const field=LIMB_FIELDS[key];
          if(!field||!valid(amount,field.min,field.max))fail();
          profile.avatar.limbs[group][key]=amount;
        }
      }
    }
  }
  for(const key of Object.keys(REGIONS)){
    const item=value.profile[key];
    if(!item||!triple(item.dimensions,10,2000)||!valid(item.gap,0,100))fail();
    const details={};
    for(const [name,{min,max}] of Object.entries(DETAILS[key])){
      const amount=item.details?.[name];
      if(amount===undefined)continue;
      if(!valid(amount,min,max))fail();
      details[name]=amount;
    }
    profile[key]={dimensions:item.dimensions,gap:item.gap,details};
    if(key==='head'&&item.foamTop!==undefined){if(!valid(item.foamTop,0,40))fail();profile.head.foamTop=item.foamTop;}
  }
  let faces=0;
  const parts=value.parts.map(part=>{
    if(!part||typeof part.name!=='string'||!part.name.trim()||part.name.length>120||!Object.hasOwn(REGIONS,part.region))fail();
    const t=part.transform;
    if(!t||!triple(t.scale,.005,50)||!triple(t.rotate,-360,360)||!triple(t.offset,-5000,5000))fail();
    const mesh=decodeFloats(part.vertices);
    faces+=mesh.length/9;if(faces>MAX_PROJECT_FACES)fail();
    const shinStyle=part.shinStyle===undefined?DEFAULT_SHIN_STYLE:part.shinStyle;
    if(part.region==='shin'&&(typeof shinStyle!=='string'||!Object.hasOwn(SHIN_STYLES,shinStyle)))fail();
    const shinSide=part.shinSide??'L';
    if(part.region==='shin'&&shinSide!=='L'&&shinSide!=='R')fail();
    if(part.group!==undefined&&(typeof part.group!=='string'||part.group.length>100||part.region!=='head'))fail();
    return {name:part.name,region:part.region,transform:t,mesh,quality:inspectMesh(mesh),...(part.group?{group:part.group}:{}),
      ...(part.region==='shin'?{shinStyle,shinSide}:{})};
  });
  const active=Number.isInteger(value.active)&&value.active>=0&&value.active<parts.length?value.active:parts.length?0:-1;
  return {profile,parts,active};
}
