import { test } from 'node:test';
import assert from 'node:assert/strict';
import { autoFit, bounds, centerMesh, demoShell, evaluate, identity, inspectMesh, parseSTL, transform, writeSTL } from '../app/geometry.mjs';
import { freshProfile, openProject, packProject } from '../app/project.mjs';

const square = Float32Array.of(-1,-1,0,1,-1,0,1,1,0,-1,-1,0,1,1,0,-1,1,0);
const helmet = centerMesh(demoShell());
const profile = freshProfile();

test('STL preserves coordinates and keeps binary headers beginning with solid readable',()=>{
  const stl=writeSTL(helmet);
  new Uint8Array(stl).set(new TextEncoder().encode('solid'));
  assert.deepEqual(parseSTL(stl),helmet);
  const ascii='solid one\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 1 1 0\nendloop\nendfacet\nendsolid one';
  assert.equal(parseSTL(new TextEncoder().encode(ascii).buffer).length,9);
});
test('helmet stays hollow and meets requested static clearance without changing triangle topology',()=>{
  const q=inspectMesh(helmet), {dimensions,gap}=profile.head;
  assert.equal(q.closed,true);
  const t=autoFit(helmet,'head',dimensions,gap,[0,0,0],q);
  const fit=transform(helmet,t), check=evaluate(fit,'head',dimensions,gap,q,{entry:true});
  assert.equal(fit.length,helmet.length);
  assert.equal(check.collision,false);
  assert.ok(check.margin>=gap);
  assert.equal(check.entry,'blocked');
});
test('a watertight solid containing the body center is rejected',()=>{
  const a=[0,0,60],b=[-50,-50,-30],c=[50,-50,-30],d=[0,65,-30];
  const mesh=Float32Array.from([a,b,c,a,c,d,a,d,b,b,d,c].flat());
  const q=inspectMesh(mesh);
  assert.equal(q.closed,true);
  assert.throws(()=>autoFit(mesh,'head',[100,100,100],3,[0,0,0],q),/materiale/);
});
test('a flat breastplate is positioned in front of the padded torso',()=>{
  const mesh=square.map(n=>n*180),q=inspectMesh(mesh), {dimensions,gap}=profile.chest;
  const fitted=transform(mesh,autoFit(mesh,'chest',dimensions,gap,[0,0,0],q));
  assert.ok(bounds(fitted).min[2]>dimensions[2]/2+gap-.05);
  assert.equal(evaluate(fitted,'chest',dimensions,gap,q).collision,false);
});
test('a centered curved shin guard fits its body proxy',()=>{
  const {dimensions,gap}=profile.shin;
  const q=inspectMesh(helmet);
  const fitted=transform(helmet,autoFit(helmet,'shin',dimensions,gap,[0,0,0],q));
  assert.ok(evaluate(fitted,'shin',dimensions,gap,q).margin>=gap);
});
test('project round trip keeps multiple original meshes and editable independent transforms',()=>{
  const t=identity();t.scale=[1.2,1.3,1.4];t.rotate=[90,0,0];t.offset=[0,10,5];
  const parts=[{name:'Hełm',region:'head',mesh:helmet,transform:t},{name:'Płyta',region:'chest',mesh:square,transform:identity()}];
  const restored=openProject(new TextDecoder().decode(packProject(profile,parts,1)));
  assert.deepEqual(restored.profile,profile);assert.equal(restored.active,1);
  assert.deepEqual(restored.parts[0].mesh,helmet);
  assert.deepEqual(restored.parts[0].transform,t);
  assert.equal(restored.parts[1].region,'chest');
  assert.throws(()=>openProject('{"version":99}'),/Nieprawidłowy/);
});

test('a front shin plate is placed outside the leg while the wrap mode keeps its center',()=>{
  const {dimensions,gap}=profile.shin;
  const plate=square.map((n,i)=>n*[52,170,1][i%3]);
  const quality=inspectMesh(plate);
  const fitted=transform(plate,autoFit(plate,'shin',dimensions,gap,[0,0,0],quality,'front'));
  assert.ok(bounds(fitted).min[2]>=dimensions[2]/2+gap-.01);
  assert.equal(evaluate(fitted,'shin',dimensions,gap,quality).collision,false);
  const wrap=autoFit(helmet,'shin',dimensions,gap,[0,0,0],inspectMesh(helmet),'wrap');
  assert.deepEqual(wrap.offset,[0,0,0]);
});

test('each shin style persists and legacy shin parts default to wrap',()=>{
  const parts=[
    {name:'Płyta',region:'shin',shinStyle:'front',mesh:square,transform:identity()},
    {name:'Obejma',region:'shin',shinStyle:'wrap',mesh:helmet,transform:identity()}
  ];
  const text=new TextDecoder().decode(packProject(profile,parts,0));
  assert.deepEqual(openProject(text).parts.map(p=>p.shinStyle),['front','wrap']);
  const legacy=JSON.parse(text);
  delete legacy.parts[0].shinStyle;
  assert.equal(openProject(JSON.stringify(legacy)).parts[0].shinStyle,'wrap');
  legacy.parts[0].shinStyle='invalid';
  assert.throws(()=>openProject(JSON.stringify(legacy)),/Nieprawidłowy/);
});

test('nose projection changes a helmet collision that an ordinary head clears',async()=>{
  const {humanFittingVolumes}=await import('../app/human.mjs');
  const person=freshProfile(), {dimensions,gap}=person.head;
  const visor=square.map((x,i)=>i%3===2?127:i%3===1?x*18-23:x*20);
  const check=()=>evaluate(visor,'head',dimensions,gap,inspectMesh(visor),{
    avatar:humanFittingVolumes(person,'head')
  }).collision;
  assert.equal(check(),false);
  person.head.details.noseProjection=75;
  assert.equal(check(),true);
});

test('helmet fitting clears the measured mannequin and flags its narrow opening',async()=>{
  const {resizeHeadCircumference,headCircumference}=await import('../app/avatar.mjs');
  const {humanFittingVolumes}=await import('../app/human.mjs');
  const person=freshProfile();
  person.head.dimensions=resizeHeadCircumference(person.head.dimensions,590);
  assert.ok(Math.abs(headCircumference(person.head.dimensions)-590)<1e-6);
  const {dimensions,gap}=person.head, avatar=humanFittingVolumes(person,'head'), q=inspectMesh(helmet);
  const t=autoFit(helmet,'head',dimensions,gap,[0,0,0],q,'wrap',avatar);
  const fit=evaluate(transform(helmet,t),'head',dimensions,gap,q,{avatar,entry:true});
  assert.equal(fit.collision,false);
  assert.ok(fit.margin>=gap-.02);
  assert.equal(fit.entry,'blocked');
});

test('body types affect torso shape and the unmodified full mannequin follows stature',async()=>{
  const {humanScene}=await import('../app/human.mjs');
  const person=freshProfile();
  person.avatar.type='male';
  const male=bounds(humanScene(person,'torso','standing').body);
  person.avatar.type='female';
  const female=bounds(humanScene(person,'torso','standing').body);
  assert.notEqual(male.size[0],female.size[0]);
  assert.notDeepEqual(female,male);
  for(const stature of [1700,1850]){
    person.avatar.stature=stature;
    const body=bounds(humanScene(person,'full','standing').body);
    assert.ok(Math.abs(body.max[1]-body.min[1]-stature)<1);
  }
});

test('mannequin overrides survive project save and old projects retain their dimensions',()=>{
  const person=freshProfile();
  person.avatar={type:'female',stature:1680};
  person.head.details={noseProjection:46,earSpan:177};
  person.chest.details={waist:732,bustProjection:38};
  const saved=new TextDecoder().decode(packProject(person,[],-1));
  assert.deepEqual(openProject(saved).profile,person);
  const legacy=JSON.parse(saved);
  delete legacy.profile.avatar;
  for(const key of ['head','chest','shin'])delete legacy.profile[key].details;
  const old=openProject(JSON.stringify(legacy)).profile;
  assert.deepEqual(old.chest.dimensions,person.chest.dimensions);
  assert.equal(old.avatar.type,'neutral');
  assert.deepEqual(old.head.details,{});
});

test('the rig supplies a separate mesh for every named body area and all pose presets',async()=>{
  const {BODY_VIEWS,POSES,humanScene}=await import('../app/human.mjs');
  const person=freshProfile();
  for(const view of Object.keys(BODY_VIEWS)){
    const {body}=humanScene(person,view,'standing');
    assert.ok(body.length>0,view);
    assert.ok(body.every(Number.isFinite),view);
  }
  const standing=humanScene(person,'full','standing').body;
  for(const pose of Object.keys(POSES).filter(p=>p!=='standing')){
    const {body}=humanScene(person,'full',pose);
    assert.equal(body.length,standing.length);
    assert.notDeepEqual(body,standing,pose);
  }
  person.head.dimensions[1]=235;
  assert.ok(Math.abs(bounds(humanScene(person,'head','standing').body).size[1]-235)<.1);
});

test('left and right shin parts attach to different legs and follow the pose without modifying export geometry',async()=>{
  const {humanScene}=await import('../app/human.mjs');
  const person=freshProfile(), before=square.slice();
  const left=humanScene(person,'full','standing',square,'shin','L').mesh;
  const right=humanScene(person,'full','standing',square,'shin','R').mesh;
  assert.ok(bounds(left).center[0]>0);
  assert.ok(bounds(right).center[0]<0);
  assert.notDeepEqual(humanScene(person,'full','step',square,'shin','L').mesh,left);
  assert.deepEqual(square,before);
  const part={name:'Prawa goleń',region:'shin',shinSide:'R',mesh:square,transform:identity()};
  const project=new TextDecoder().decode(packProject(person,[part],0));
  assert.equal(openProject(project).parts[0].shinSide,'R');
});

test('measurement editor changes only the chosen side and persists compound lengths',async()=>{
  const {setMeasurement,measurementFields}=await import('../app/measurements.mjs');
  const {humanScene}=await import('../app/human.mjs');
  const person=freshProfile();
  const left=humanScene(person,'upperarm.L','standing').body.slice();
  const right=humanScene(person,'upperarm.R','standing').body.slice();
  setMeasurement(person,'armR','bicep',430);
  assert.deepEqual(humanScene(person,'upperarm.L','standing').body,left);
  assert.notDeepEqual(humanScene(person,'upperarm.R','standing').body,right);
  setMeasurement(person,'armR','total',680);
  const values=Object.fromEntries(measurementFields(person,'armR').map(f=>[f.key,f.value]));
  assert.ok(Math.abs(values.upperArmLength+values.forearmLength-680)<1e-8);
  setMeasurement(person,'legL','lowerLegLength',430);
  const restored=openProject(new TextDecoder().decode(packProject(person,[],-1))).profile;
  assert.deepEqual(restored,person);
  assert.throws(()=>setMeasurement(person,'legR','calf',NaN));
  assert.throws(()=>setMeasurement(person,'armR','wrist',-10));
  const malformed=JSON.parse(new TextDecoder().decode(packProject(person,[],-1)));
  malformed.profile.avatar.limbs.armR.bicep='430';
  assert.throws(()=>openProject(JSON.stringify(malformed)));
});

test('default standing anatomy is symmetric with a short neck and attached seams',async()=>{
  const {profileDetails}=await import('../app/avatar.mjs');
  const {humanScene}=await import('../app/human.mjs');
  const profile=freshProfile();
  assert.ok(profileDetails(profile,'chest').neckLength<=45);
  const left=bounds(humanScene(profile,'shin.L','standing').body);
  const right=bounds(humanScene(profile,'shin.R','standing').body);
  assert.ok(Math.abs(left.center[0]+right.center[0])<.1);
  assert.ok(Math.abs(left.center[1]-right.center[1])<.1);
  const standing=humanScene(profile,'full','standing');
  assert.ok(standing.seams.length>100);
  assert.ok(standing.seams.every(Number.isFinite));
  assert.notDeepEqual(humanScene(profile,'full','reach').seams,standing.seams);
});
