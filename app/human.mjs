import asset from './human-data.mjs';
import {bounds} from './geometry.mjs';
import {detailValues, profileDetails, limbValues, headCircumference, ellipsePerimeter} from './avatar.mjs';

const decode=(data,Type)=>new Type(Uint8Array.from(atob(data),ch=>ch.charCodeAt(0)).buffer);
const base=decode(asset.vertices,Float32Array);
const faces=decode(asset.faces,Uint16Array);
const faceRegions=decode(asset.faceRegions,Uint8Array);
const vertexRegions=decode(asset.vertexRegions,Uint8Array);
const skinIndices=decode(asset.skinIndices,Uint8Array);
const skinWeights=decode(asset.skinWeights,Float32Array);
const targets=Object.fromEntries(Object.entries(asset.targets).map(([key,{indices,values}])=>[
  key,{indices:decode(indices,Uint16Array),values:decode(values,Float32Array)}
]));
const joints=Object.fromEntries(asset.joints.map(([name,,...point])=>[name,point]));

export const BODY_VIEWS={
  full:'Cała sylwetka',torso:'Cały tułów',head:'Głowa',neck:'Szyja',chest:'Klatka piersiowa',waist:'Talia',pelvis:'Biodra',
  'upperarm.L':'Lewe ramię','forearm.L':'Lewe przedramię','hand.L':'Lewa dłoń',
  'upperarm.R':'Prawe ramię','forearm.R':'Prawe przedramię','hand.R':'Prawa dłoń',
  'thigh.L':'Lewe udo','shin.L':'Lewa goleń','foot.L':'Lewa stopa',
  'thigh.R':'Prawe udo','shin.R':'Prawa goleń','foot.R':'Prawa stopa'
};
export const POSES={standing:'Stojąca',side:'T-pose',reach:'Ręce do przodu',step:'Krok'};
export const fittingView=(region,side='L')=>region==='shin'?'shin.'+side:region==='chest'?'torso':region;
const GROUND=-8.1676, CROWN=8.4913, CHIN=6.12;
const clamp=(n,a,b)=>Math.min(b,Math.max(a,n));
const lerp=(a,b,t)=>a+(b-a)*t;
const smooth=(a,b,n)=>{const t=clamp((n-a)/(b-a),0,1);return t*t*(3-2*t);};
const bell=(value,center,radius)=>Math.exp(-(((value-center)/radius)**2));

function addTarget(vertices,key,amount,preserveHeight=false){
  if(!amount)return;
  const {indices,values}=targets[key];
  for(let i=0;i<indices.length;i++){
    const k=indices[i]*3;
    for(let axis=0;axis<3;axis++)if(axis!==1||!preserveHeight)vertices[k+axis]+=values[i*3+axis]*amount;
  }
}
function targetForMillimetres(vertices,key,amount,axis,unit){
  const {values}=targets[key];
  let peak=0;
  for(let i=axis;i<values.length;i+=3)peak=Math.max(peak,Math.abs(values[i]));
  if(peak>0)addTarget(vertices,key,clamp(amount/(peak*unit),-2,7));
}

function measurementMap(profile){
  const {stature,type}=profile.avatar;
  const [hw,hh,hd]=profile.head.dimensions, [tw,th,td]=profile.chest.dimensions, [sw,sh,sd]=profile.shin.dimensions;
  const head=profileDetails(profile,'head'), torso=profileDetails(profile,'chest'), shin=profileDetails(profile,'shin');
  const defaultHead=detailValues('head',{dimensions:profile.head.dimensions},type);
  const defaultTorso=detailValues('chest',{dimensions:profile.chest.dimensions},type);
  const defaultShin=detailValues('shin',{dimensions:profile.shin.dimensions},type);
  const unit=stature/(CROWN-GROUND);
  const ground=-stature/2, crown=stature/2, chin=crown-hh;
  const neckLength=torso.neckLength;
  const calfLength=Math.min(sh,(stature-hh)*.40);
  const ankle=ground+stature*.043;
  const knee=ankle+calfLength;
  const collar=Math.max(knee+100,chin-neckLength);
  const hip=clamp(profile.shin.details?.thighLength===undefined?collar-th:knee+shin.thighLength,knee+30,collar-30);
  const levels=[[GROUND,ground],[-7.448,ankle],[-3.695,knee],[.486,hip],[5.74,collar],[CHIN,chin],[CROWN,crown]];
  function height(y){
    for(let i=1;i<levels.length;i++){
      const [a,x]=levels[i-1], [b,z]=levels[i];
      if(y<=b||i===levels.length-1)return lerp(x,z,(y-a)/(b-a));
    }
  }
  return {profile,head,torso,shin,defaultHead,defaultTorso,defaultShin,unit,height,chin,crown,
    headScale:[hw/1.50,hh/(CROWN-CHIN),hd/1.95],torsoScale:[tw/3.5,th/5.25,td/2.3],shinScale:[sw/1.10,sh/3.75,sd/1.15]};
}

function regionFactor(y,fields,current,defaults){
  let weight=0, factor=0;
  for(const [key,center,radius] of fields){
    const w=bell(y,center,radius);
    weight+=w;factor+=w*(current[key]/defaults[key]-1);
  }
  return 1+factor/Math.max(1,weight);
}
function shapePoint(point,region,m){
  let [x,y,z]=point;
  const {head,defaultHead,defaultTorso,defaultShin,unit,height,headScale,torsoScale,shinScale}=m;
  const torso=/^(upperarm|forearm|hand)\./.test(region)?limbValues(m.profile,'arm',region.at(-1)):m.torso;
  const shin=/^(thigh|shin|foot)\./.test(region)?limbValues(m.profile,'leg',region.at(-1)):m.shin;
  const az=Math.abs(x), side=x<0?-1:1;
  if(y>5.72&&az<1.22){
    const blend=smooth(5.72,CHIN,y), neck=1+(torso.neck/defaultTorso.neck-1)*bell(y,5.98,.25)+(torso.neckBase/defaultTorso.neckBase-1)*bell(y,5.72,.18);
    const ears=smooth(.59,.79,az)*bell(y,7.22,.37);
    const jaw=bell(y,6.50,.33)*smooth(.20,.80,z);
    const eyes=bell(az,.33,.22)*bell(y,7.29,.19)*smooth(1.0,1.45,z);
    const lips=bell(y,6.61,.17)*bell(az,.15,.36)*smooth(1.04,1.50,z);
    const chin=bell(y,6.28,.20)*smooth(.65,1.47,z);
    const face=smooth(.65,1.48,z)*bell(y,6.93,.73);
    const outX=x*headScale[0]+side*((head.earSpan-defaultHead.earSpan)*ears+(head.eyeSpacing-defaultHead.eyeSpacing)*eyes)/2
      +x*headScale[0]*(jaw*(head.jawWidth/defaultHead.jawWidth-1)+lips*(head.mouthWidth/defaultHead.mouthWidth-1));
    const outY=height(y)+(head.eyeHeight-defaultHead.eyeHeight)*eyes
      +(y-7.22)*headScale[1]*(head.earHeight/defaultHead.earHeight-1)*ears;
    const outZ=.57*unit+(z-.57)*headScale[2]+(head.faceDepth-defaultHead.faceDepth)*face
      +(head.chinDepth-defaultHead.chinDepth)*chin+(z-.40)*headScale[2]*(head.earDepth/defaultHead.earDepth-1)*ears;
    return [lerp(x*unit*neck,outX,blend),lerp(height(y),outY,blend),lerp(z*unit*neck,outZ,blend)];
  }
  if(/^(upperarm|forearm|hand)\./.test(region)){
    const suffix=region.at(-1), shoulder=joints['upperarm01.'+suffix], elbow=joints['lowerarm01.'+suffix];
    const wrist=[side*4.31185,2.4518125,1.75655];
    const map=p=>[p[0]*unit,height(p[1]),p[2]*unit];
    const sh=map(shoulder),el=map(elbow),wr=map(wrist),position=map(point);
    const vector=(a,b)=>b.map((v,i)=>v-a[i]);
    const upper=vector(sh,el),lower=vector(el,wr);
    const upperLength=Math.hypot(...upper),lowerLength=Math.hypot(...lower);
    const u=upper.map(v=>v/upperLength),v=lower.map(n=>n/lowerLength);
    const projection=(p,o,d)=>p.reduce((sum,n,i)=>sum+(n-o[i])*d[i],0);
    const alongUpper=clamp(projection(position,sh,u)/upperLength,0,1);
    const alongLower=clamp(projection(position,el,v)/lowerLength,0,1);
    const forearm=region.startsWith('forearm'),hand=region.startsWith('hand');
    const progress=forearm||hand?1:alongUpper;
    const lowerProgress=hand?1:forearm?alongLower:0;
    const thick=hand?torso.handWidth/defaultTorso.handWidth:forearm?
      lerp(torso.forearm/defaultTorso.forearm,torso.wrist/defaultTorso.wrist,alongLower):
      lerp(lerp(torso.upperArmTop/defaultTorso.upperArmTop,torso.bicep/defaultTorso.bicep,smooth(0,.45,alongUpper)),torso.elbow/defaultTorso.elbow,smooth(.65,1,alongUpper));
    const shapeFields=m.profile.avatar.shapes?.['arm'+suffix]??{};
    const shape=forearm||hand?lerp(shapeFields.forearm??100,shapeFields.wrist??100,alongLower)/100:
      lerp(shapeFields.upperArmTop??100,shapeFields.bicep??100,smooth(0,.5,alongUpper))/100;
    const origin=forearm||hand?el:sh,axis=forearm||hand?v:u;
    const lateral=[-axis[1],axis[0],0],l=Math.hypot(...lateral);lateral.forEach((n,i)=>lateral[i]=n/l);
    const depth=[axis[1]*lateral[2]-axis[2]*lateral[1],axis[2]*lateral[0]-axis[0]*lateral[2],axis[0]*lateral[1]-axis[1]*lateral[0]];
    const wide=projection(position,origin,lateral),deep=projection(position,origin,depth);
    const shapeNorm=ellipsePerimeter(Math.sqrt(shape),1/Math.sqrt(shape))/Math.PI;
    const along=projection(position,origin,axis);
    const shoulderOffset=side*((torso.shoulders-defaultTorso.shoulders)/2+(torso.singleShoulder-defaultTorso.singleShoulder)*.65);
    return position.map((n,i)=>n
      +u[i]*(torso.upperArmLength-upperLength)*progress
      +v[i]*(torso.forearmLength-lowerLength)*lowerProgress
      +(n-origin[i]-axis[i]*along)*(thick-1)
      +wide*lateral[i]*thick*(Math.sqrt(shape)/shapeNorm-1)+deep*depth[i]*thick*(1/Math.sqrt(shape)/shapeNorm-1)
      +(hand?v[i]*(torso.handLength-defaultTorso.handLength)*smooth(0,unit*1.8,projection(position,wr,v)):0)
      +(i===0?shoulderOffset:0));
  }
  if(/^(thigh|shin|foot)\./.test(region)){
    const t=smooth(-3.695,-7.448,y);
    const centerX=side*lerp(1.58,2.196,t), centerZ=lerp(.32,0,t);
    const ratio=regionFactor(y,[['knee',-3.695,.50],['calf',-5.1,1.05],['ankle',-7.45,.46],['thigh',-1.6,1.6]],shin,defaultShin);
    const mix=smooth(-3,-4.45,y);
    const lx=lerp(unit,shinScale[0],mix)*ratio, lz=lerp(unit,shinScale[2],mix)*ratio;
    const stretch=region.startsWith('foot')?shin.footLength/defaultShin.footLength:1;
    const thighDelta=shin.thighLength-m.shin.thighLength;
    const calfDelta=(shin.lowerLegLength??m.profile.shin.dimensions[1])-m.profile.shin.dimensions[1];
    const legHeight=height(y)-thighDelta*smooth(.486,-3.695,y)-calfDelta*smooth(-3.695,-7.448,y);
    return [centerX*unit+(x-centerX)*lx,legHeight,centerZ*unit+(z-centerZ)*lz*stretch];
  }
  const ratio=regionFactor(y,[['chestCirc',4.45,1.0],['highBust',4.91,.5],['underBust',3.65,.62],
    ['waist',2.25,.79],['highHip',1.46,.7],['hips',.68,.85]],torso,defaultTorso);
  const shoulder=bell(y,5.24,.62)*smooth(.52,1.75,az);
  const back=smooth(.08,-.70,z)*bell(y,4.1,1.18);
  const front=smooth(.10,.93,z)*bell(y,4.1,.95);
  const across=torso.acrossChest/defaultTorso.acrossChest-1;
  const backWide=torso.backWidth/defaultTorso.backWidth-1;
  return [x*torsoScale[0]*ratio*(1+front*across+back*backWide)+side*shoulder*(torso.shoulders-defaultTorso.shoulders)/2,
    height(y)+front*(torso.breastHeight??0)*bell(y,4.15,.60),
    z*torsoScale[2]*ratio+front*(torso.bustProjection-defaultTorso.bustProjection)
      +front*bell(y,4.15,.60)*(torso.breastSize/100-1)*unit*.7
      -smooth(.1,-.6,z)*bell(y,.5,.85)*(torso.buttSize/100-1)*unit*.6
      +shoulder*.16*(torso.armhole-defaultTorso.armhole)];
}

// Rotations are in rest-space axes. The upstream skin weights blend the
// parent and child transforms at each joint.
const R0=[1,0,0,0,1,0,0,0,1];
const mul=(a,b)=>Array.from({length:9},(_,i)=>{
  const r=Math.floor(i/3)*3,c=i%3;
  return a[r]*b[c]+a[r+1]*b[c+3]+a[r+2]*b[c+6];
});
const rotate=(r,[x,y,z])=>[r[0]*x+r[1]*y+r[2]*z,r[3]*x+r[4]*y+r[5]*z,r[6]*x+r[7]*y+r[8]*z];
const apply=(t,p)=>rotate(t.r,p).map((v,i)=>v+t.o[i]);
function rotation(x,z){
  const a=x*Math.PI/180,b=z*Math.PI/180;
  const c=Math.cos(a),s=Math.sin(a),d=Math.cos(b),e=Math.sin(b);
  return mul([d,-e,0,e,d,0,0,0,1],[1,0,0,0,c,-s,0,s,c]);
}
function angles(name,pose){
  const side=name.endsWith('.L')?1:-1;
  if(name.startsWith('upperarm')){
    if(pose==='side')return [0,side*45];
    if(pose==='reach')return [-40,-side*19];
    return [pose==='step'?side*14:0,-side*25];
  }
  if(name.startsWith('lowerarm'))return [pose==='reach'?-32:pose==='side'?57:45,pose==='side'?side*5:0];
  if(pose==='step'&&name.startsWith('upperleg'))return [-side*14,0];
  if(pose==='step'&&name.startsWith('lowerleg'))return [side===1?17:6,0];
  return [0,0];
}

let cachedKey='', cachedRest;
function rest(profile){
  const key=JSON.stringify(profile);
  if(cachedKey===key)return cachedRest;
  const m=measurementMap(profile), vertices=new Float32Array(base);
  if(profile.avatar.type!=='neutral')addTarget(vertices,profile.avatar.type,1,true);
  for(const [name,axis] of [['noseProjection',2],['noseWidth',0],['noseLength',1],['noseHeight',1]])
    targetForMillimetres(vertices,name,m.head[name]-m.defaultHead[name],axis,m.headScale[axis]);
  const output=new Float32Array(vertices.length);
  for(let i=0;i<vertices.length;i+=3)
    output.set(shapePoint(vertices.subarray(i,i+3),asset.regions[vertexRegions[i/3]],m),i);
  blendTransitions(output,vertices,m.unit);
  applyCrossSectionShapes(output,m);
  calibrateGirths(output,profile);
  calibrateHead(output,m);
  let shoulderReference=output;
  if(m.profile.avatar.limbs&&Object.keys(m.profile.avatar.limbs).length){
    const referenceMap={...m,profile:{...m.profile,avatar:{...m.profile.avatar,limbs:{}}}};
    shoulderReference=new Float32Array(vertices.length);
    for(let i=0;i<vertices.length;i+=3)shoulderReference.set(shapePoint(vertices.subarray(i,i+3),asset.regions[vertexRegions[i/3]],referenceMap),i);
    blendTransitions(shoulderReference,vertices,m.unit);
    calibrateGirths(shoulderReference,referenceMap.profile);
  }
  let shoulderShift=0;
  const shoulderWeights=Array.from({length:output.length/3},(_,index)=>{
    let armWeight=0;
    for(let k=0;k<4;k++)if(/^(upperarm|lowerarm)/.test(asset.joints[skinIndices[index*4+k]][0]))armWeight+=skinWeights[index*4+k];
    const x=base[index*3],y=base[index*3+1];
    const root=smooth(.4,1.8,Math.abs(x))*smooth(4.55,5.05,y)*(1-smooth(5.5,5.74,y));
    return armWeight+(1-armWeight)*root;
  });
  for(let pass=0;pass<4;pass++){
    const section=horizontalSection(shoulderReference,m.height(5.15));
    const width=Math.max(...section.map(p=>p[0]))-Math.min(...section.map(p=>p[0]));
    const shift=(m.torso.shoulders-width)/2;shoulderShift+=shift;
    for(let i=0;i<output.length;i+=3){
      const delta=Math.sign(base[i])*shift*shoulderWeights[i/3];
      output[i]+=delta;if(shoulderReference!==output)shoulderReference[i]+=delta;
    }
  }
  calibrateGirths(output,profile);
  const pivots=asset.joints.map(([name,,...point])=>shapePoint(point,
    name.startsWith('upperarm')?'upperarm'+name.slice(-2):name.startsWith('lowerarm')?'forearm'+name.slice(-2):
      name.startsWith('upperleg')?'thigh'+name.slice(-2):name.startsWith('lowerleg')?'shin'+name.slice(-2):
        name.startsWith('foot')?'foot'+name.slice(-2):name,m));
  asset.joints.forEach(([name],i)=>{if(/^(upperarm|lowerarm)/.test(name))pivots[i][0]+=(name.endsWith('.L')?1:-1)*shoulderShift;});
  cachedKey=key;cachedRest={vertices:output,pivots,m,anatomy:{},anchors:{},poses:{}};
  return cachedRest;
}
function matrices(pivots,pose){
  const all=[];
  for(let i=0;i<asset.joints.length;i++){
    const [name,parent]=asset.joints[i], pivot=pivots[i],r=rotation(...angles(name,pose));
    const moved=rotate(r,pivot), local={r,o:pivot.map((v,j)=>v-moved[j])};
    if(parent<0)all.push(local);
    else all.push({r:mul(all[parent].r,r),o:apply(all[parent],local.o)});
  }
  return all;
}
function posedVertices(restVertices,transforms){
  const output=new Float32Array(restVertices.length);
  for(let i=0;i<restVertices.length/3;i++){
    const p=restVertices.subarray(i*3,i*3+3);
    for(let j=0;j<4;j++){
      const w=skinWeights[i*4+j];
      if(!w)continue;
      const result=apply(transforms[skinIndices[i*4+j]],p);
      for(let axis=0;axis<3;axis++)output[i*3+axis]+=result[axis]*w;
    }
  }
  return output;
}
function triangles(vertices,regions){
  const result=[];
  for(let i=0;i<faces.length;i+=3){
    if(regions&&!regions.has(asset.regions[faceRegions[i/3]]))continue;
    for(let j=0;j<3;j++){
      const at=faces[i+j]*3;
      result.push(vertices[at],vertices[at+1],vertices[at+2]);
    }
  }
  return Float32Array.from(result);
}

function headSlice(vertices,level){
  const result=[];
  for(let i=0;i<faces.length;i+=3){
    const points=Array.from({length:3},(_,j)=>vertices.subarray(faces[i+j]*3,faces[i+j]*3+3));
    if(points.every(p=>p[1]<level))continue;
    const polygon=[];
    for(let j=0;j<3;j++){
      const a=points[j],b=points[(j+1)%3];
      if(a[1]>=level)polygon.push(a);
      if((a[1]>=level)!==(b[1]>=level)){
        const t=(level-a[1])/(b[1]-a[1]);
        polygon.push([lerp(a[0],b[0],t),level,lerp(a[2],b[2],t)]);
      }
    }
    for(let j=1;j+1<polygon.length;j++)result.push(...polygon[0],...polygon[j],...polygon[j+1]);
  }
  return Float32Array.from(result);
}
function regionMesh(vertices,region,state,side){
  if(region==='head')return headSlice(vertices,state.m.chin);
  const group=region==='chest'?['chest']: [fittingView(region,side)];
  return triangles(vertices,new Set(group));
}
function anchorFor(state,region,side){
  if(region==='head')return [0,(state.m.chin+state.m.crown)/2,.57*state.m.unit];
  const key=fittingView(region,side);
  return state.anchors[key]??=bounds(regionMesh(state.vertices,region,state,side)).center;
}
const attachmentBone=(region,side)=>region==='head'?'head':region==='shin'?'lowerleg01.'+side:'root';

export function humanScene(profile,view,pose,armor,armorRegion,side='L'){
  const state=rest(profile);
  if(!state.poses[pose]){
    const transforms=matrices(state.pivots,pose);
    state.poses[pose]={transforms,vertices:posedVertices(state.vertices,transforms),views:{}};
  }
  const {transforms,vertices,views}=state.poses[pose];
  const body=views[view]??=(view==='head'?headSlice(vertices,state.m.chin)
    :triangles(vertices,view==='full'?null:new Set(view==='torso'?['chest','waist','pelvis','neck']: [view])));
  let mesh=armor;
  if(armor){
    const anchor=anchorFor(state,armorRegion,side);
    const t=transforms[asset.joints.findIndex(([name])=>name===attachmentBone(armorRegion,side))];
    mesh=new Float32Array(armor.length);
    for(let i=0;i<armor.length;i+=3)
      mesh.set(apply(t,[armor[i]+anchor[0],armor[i+1]+anchor[1],armor[i+2]+anchor[2]]),i);
  }
  const context=views.full??=triangles(vertices,null);
  const seams=views.seams??=mannequinSeams(state.vertices,vertices);
  return {body,context,mesh,seams};
}

function enclosingVolumes(mesh){
  // Group complete triangles into local bands. The resulting ellipsoids
  // enclose every triangle in their group, including nose and ears.
  const box=bounds(mesh),groups=new Map();
  for(let i=0;i<mesh.length;i+=9){
    const x=(mesh[i]+mesh[i+3]+mesh[i+6])/3;
    const y=(mesh[i+1]+mesh[i+4]+mesh[i+7])/3;
    const z=(mesh[i+2]+mesh[i+5]+mesh[i+8])/3;
    const band=clamp(Math.floor((y-box.min[1])/box.size[1]*9),0,8);
    const depth=z>box.max[2]-box.size[2]*.19?2:z>box.center[2]?1:0;
    const side=depth===2?0:Math.abs(x)>box.size[0]*.29?Math.sign(x):0;
    const key=band+'|'+depth+'|'+side;
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(...mesh.subarray(i,i+9));
  }
  return [...groups.values()].map(points=>{
    const {center,size}=bounds(points);
    const radii=size.map(n=>Math.max(1,n/2));
    let extent=1;
    for(let i=0;i<points.length;i+=3)extent=Math.max(extent,
      Math.hypot(...radii.map((r,axis)=>(points[i+axis]-center[axis])/r)));
    return {center,radii:radii.map(r=>r*extent)};
  });
}

export function humanFittingVolumes(profile,region,side='L'){
  const state=rest(profile),key=fittingView(region,side);
  if(state.anatomy[key])return state.anatomy[key];
  const center=anchorFor(state,region,side);
  const mesh=regionMesh(state.vertices,region,state,side).map((value,i)=>value-center[i%3]);
  if(region==='head'&&profile.head.foamTop){
    const top=bounds(mesh).max[1],height=profile.head.dimensions[1];
    for(let i=1;i<mesh.length;i+=3)mesh[i]+=profile.head.foamTop*smooth(top-height*.22,top,mesh[i]);
  }
  const envelope=enclosingVolumes(mesh);
  const core=bounds(mesh).size.map(n=>n*.30);
  envelope.push({center:[0,0,0],radii:core});
  return state.anatomy[key]=envelope;
}

// Cut seams on the rest surface and interpolate their posed positions, so
// lines stay attached to the skin in every pose and after measurement edits.
function mannequinSeams(restVertices,posed){
  const cuts=[
    {axis:1,value:5.80,filter:(x,y)=>Math.abs(x)<.85},
    {axis:1,value:3.72,filter:(x,y)=>Math.abs(x)<1.7},
    {axis:1,value:2.22,filter:(x,y)=>Math.abs(x)<1.7},
    {axis:1,value:.62,filter:(x,y)=>Math.abs(x)<1.9},
    ...[-1,1].flatMap(side=>[
      {axis:1,value:-3.695,filter:x=>x*side>0},
      {axis:1,value:-7.30,filter:x=>x*side>0},
      {axis:0,value:side*2.03,filter:(x,y)=>y>4.1},
      {axis:0,value:side*3.13,filter:(x,y)=>y>2.7&&y<4.2},
      {axis:0,value:side*4.48,filter:(x,y)=>y>1&&y<3.2}
    ])
  ];
  const result=[];
  for(let f=0;f<faces.length;f+=3){
    const ids=[faces[f],faces[f+1],faces[f+2]];
    for(const cut of cuts){
      const hits=[];
      for(let j=0;j<3;j++){
        const a=ids[j],b=ids[(j+1)%3];
        const av=base[a*3+cut.axis]-cut.value,bv=base[b*3+cut.axis]-cut.value;
        if((av<0)===(bv<0))continue;
        const t=av/(av-bv);
        const x=lerp(base[a*3],base[b*3],t),y=lerp(base[a*3+1],base[b*3+1],t);
        if(!cut.filter(x,y))continue;
        hits.push([0,1,2].map(axis=>lerp(posed[a*3+axis],posed[b*3+axis],t)));
      }
      if(hits.length===2)result.push(...hits[0],...hits[1]);
    }
  }
  return Float32Array.from(result);
}
// Circumference controls use surface-plane intersections, not ellipsoid
// assumptions. A convex perimeter is appropriate for a taut measuring tape.
function perimeter(points){
  const sorted=points.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  const turn=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
  const half=arr=>{const h=[];for(const p of arr){while(h.length>1&&turn(h.at(-2),h.at(-1),p)<=0)h.pop();h.push(p);}return h;};
  if(sorted.length<3)return 0;
  const hull=[...half(sorted).slice(0,-1),...half([...sorted].reverse()).slice(0,-1)];
  return hull.reduce((sum,p,i)=>sum+Math.hypot(p[0]-hull[(i+1)%hull.length][0],p[1]-hull[(i+1)%hull.length][1]),0);
}
function calibrateGirths(vertices,profile){
  const controls=[];
  const torso=profile.chest.details;
  for(const [key,level,width] of [['neck',5.98,.15],['neckBase',5.74,.15],['highBust',4.91,.5],['chestCirc',4.45,.8],['underBust',3.65,.65],['waist',2.25,.75],['highHip',1.46,.55],['hips',.68,.65]]){
    if(torso[key]!==undefined||profile.avatar.shapes?.chest?.[key]!==undefined)controls.push({value:torso[key]??profileDetails(profile,'chest')[key],level,width,axis:1,axes:[0,2],accept:i=>Math.abs(base[i*3])<(level>5.5?.9:1.9)});
  }
  for(const side of ['L','R']){
    const sign=side==='L'?1:-1;
    const leg={...profile.shin.details,...profile.avatar.limbs?.['leg'+side]};
    for(const [key,level,width] of [['thigh',-1.6,.85],['knee',-3.695,.5],['calf',-5.1,.8],['ankle',-7.45,.4]])
      if(leg[key]!==undefined||profile.avatar.shapes?.['leg'+side]?.[key]!==undefined)controls.push({value:leg[key]??limbValues(profile,'leg',side)[key],level,width,axis:1,axes:[0,2],accept:i=>base[i*3]*sign>0});
  }
  for(let iteration=0;iteration<5;iteration++)for(const control of controls){
    const {axis,axes,level,width,accept,value}=control;
    const worldLevel=measurementMap(profile).height(level);
    const points=[];
    for(let f=0;f<faces.length;f+=3)for(let j=0;j<3;j++){
      const a=faces[f+j],b=faces[f+(j+1)%3];
      if(!accept(a)||!accept(b))continue;
      const av=vertices[a*3+axis]-worldLevel,bv=vertices[b*3+axis]-worldLevel;
      if((av<0)===(bv<0))continue;
      const t=av/(av-bv);
      points.push(axes.map(k=>lerp(vertices[a*3+k],vertices[b*3+k],t)));
    }
    const current=perimeter(points);
    if(current<1)continue;
    const factor=clamp(value/current,.5,2);
    const center=axes.map((_,k)=>(Math.min(...points.map(p=>p[k]))+Math.max(...points.map(p=>p[k])))/2);
    for(let i=0;i<vertices.length/3;i++)if(accept(i)){
      const distance=(base[i*3+axis]-level)/width;
      if(Math.abs(distance)>3)continue;
      const weight=Math.exp(-distance*distance*2);
      axes.forEach((k,j)=>vertices[i*3+k]=center[j]+(vertices[i*3+k]-center[j])*(1+(factor-1)*weight));
    }
  }
}

const neighbors=Array.from({length:base.length/3},()=>new Set());
for(let i=0;i<faces.length;i+=3)for(let j=0;j<3;j++){
  const a=faces[i+j],b=faces[i+(j+1)%3];neighbors[a].add(b);neighbors[b].add(a);
}
const transition=new Set();
for(let i=0;i<neighbors.length;i++)if([...neighbors[i]].some(j=>vertexRegions[i]!==vertexRegions[j]))transition.add(i);
for(let pass=0;pass<2;pass++)for(const i of [...transition])for(const j of neighbors[i])transition.add(j);
function blendTransitions(output,source,unit){
  let delta=output.map((v,i)=>v-source[i]*unit);
  for(let pass=0;pass<5;pass++){
    const next=delta.slice();
    for(const i of transition)for(let axis=0;axis<3;axis++){
      let sum=0;for(const j of neighbors[i])sum+=delta[j*3+axis];
      next[i*3+axis]=lerp(delta[i*3+axis],sum/neighbors[i].size,.5);
    }
    delta=next;
  }
  for(const i of transition)for(let axis=0;axis<3;axis++)output[i*3+axis]=source[i*3+axis]*unit+delta[i*3+axis];
}

function horizontalSection(vertices,level,accept=()=>true){
  const points=[];
  for(let f=0;f<faces.length;f+=3)for(let j=0;j<3;j++){
    const a=faces[f+j],b=faces[f+(j+1)%3];
    if(!accept(a)||!accept(b))continue;
    const av=vertices[a*3+1]-level,bv=vertices[b*3+1]-level;
    if((av<0)===(bv<0))continue;
    const t=av/(av-bv);
    points.push([lerp(vertices[a*3],vertices[b*3],t),lerp(vertices[a*3+2],vertices[b*3+2],t)]);
  }
  return points;
}
function calibrateHead(vertices,m){
  const level=m.height(7.65);
  const target=headCircumference(m.profile.head.dimensions);
  const current=perimeter(horizontalSection(vertices,level));
  const factor=target/current;
  for(let i=0;i<vertices.length;i+=3){
    const weight=smooth(5.74,6.40,base[i+1]);
    vertices[i]*=1+(factor-1)*weight;
    vertices[i+2]=.57*m.unit+(vertices[i+2]-.57*m.unit)*(1+(factor-1)*weight);
  }
}
export function humanAudit(profile){
  const state=rest(profile),v=state.vertices;
  const full=bounds(triangles(v)), head=bounds(headSlice(v,state.m.chin));
  const shoulders=horizontalSection(v,state.m.height(5.15));
  const shoulderWidth=Math.max(...shoulders.map(p=>p[0]))-Math.min(...shoulders.map(p=>p[0]));
  let symmetry=0;
  const buckets=new Map();
  for(let i=0;i<base.length;i+=3){
    const key=[Math.abs(base[i]).toFixed(3),base[i+1].toFixed(3),base[i+2].toFixed(3)].join('|');
    if(buckets.has(key)){
      const j=buckets.get(key);symmetry=Math.max(symmetry,Math.hypot(v[i]+v[j],v[i+1]-v[j+1],v[i+2]-v[j+2]));
    }else buckets.set(key,i);
  }
  return {stature:full.size[1],headHeight:head.size[1],headRatio:full.size[1]/head.size[1],
    headCircumference:perimeter(horizontalSection(v,state.m.height(7.65))),
    neckLength:state.m.height(CHIN)-state.m.height(5.74),shoulderWidth,symmetry,
    spineLateralDeviation:Math.max(...[.68,2.25,3.65,4.45].map(y=>{
      const p=horizontalSection(v,state.m.height(y),i=>Math.abs(base[i*3])<1.9);
      return Math.abs((Math.min(...p.map(v=>v[0]))+Math.max(...p.map(v=>v[0])))/2);
    }))};
}


function applyCrossSectionShapes(vertices,m){
 const shapes=m.profile.avatar.shapes??{};
 const levels={neck:5.98,neckBase:5.74,chestCirc:4.45,underBust:3.65,waist:2.25,highHip:1.46,hips:.68,thigh:-1.6,knee:-3.695,calf:-5.1,ankle:-7.45};
 for(let i=0;i<vertices.length;i+=3){
  const region=asset.regions[vertexRegions[i/3]],y=base[i+1],side=base[i]<0?'R':'L';
  if(y>CHIN&&shapes.head?.circ){const s=Math.sqrt(shapes.head.circ/100);vertices[i]*=s;vertices[i+2]=.57*m.unit+(vertices[i+2]-.57*m.unit)/s;continue;}
  if(/^(upperarm|forearm|hand)/.test(region))continue;
  const leg=/^(thigh|shin|foot)/.test(region),fields=leg?shapes['leg'+side]:shapes.chest;
  if(!fields)continue;
  let log=0;
  for(const [key,value] of Object.entries(fields))if(levels[key]!==undefined)log+=Math.log(value/100)*bell(y,levels[key],key.startsWith('neck')?.18:.65);
  const factor=Math.exp(log/2),center=leg?Math.sign(base[i])*lerp(1.58,2.196,smooth(-3.695,-7.448,y))*m.unit:0;
  vertices[i]=center+(vertices[i]-center)*factor;vertices[i+2]/=factor;
 }
}
export function humanGirthAudit(profile){
 const state=rest(profile),v=state.vertices;
 const result=[];
 for(const [key,y] of [['neck',5.98],['neckBase',5.74],['chestCirc',4.45],['underBust',3.65],['waist',2.25],['highHip',1.46],['hips',.68]]){
  const points=horizontalSection(v,state.m.height(y),i=>Math.abs(base[i*3])<(y>5.5?.9:1.9));
  result.push({key,requested:profile.chest.details[key]??null,actual:perimeter(points)});
 }
 return result;
}

export function fittingDimensions(profile,region,side='L'){
 const state=rest(profile);return bounds(regionMesh(state.vertices,region,state,side)).size;
}
