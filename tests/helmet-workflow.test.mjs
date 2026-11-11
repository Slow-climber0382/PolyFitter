import test from 'node:test';import assert from 'node:assert/strict';
import {freshProfile,packProject,openProject} from '../app/project.mjs';
import {humanAudit,humanGirthAudit,humanScene,humanFittingVolumes} from '../app/human.mjs';
import {resizeHeadCircumference} from '../app/avatar.mjs';
import {setMeasurement,measurementFields} from '../app/measurements.mjs';
import {kitParts,setKitTransform,fitColors} from '../app/helmet.mjs';
import {splitForPrinter} from '../app/cut.mjs';
import {bounds,identity,demoShell,transform,inspectMesh,autoFit,evaluate} from '../app/geometry.mjs';

test('three default types have adult head ratios, calibrated shoulders and lateral symmetry',()=>{
 for(const [type,width] of [['neutral',434],['male',469],['female',395]]){
  const p=freshProfile();p.avatar.type=type;const a=humanAudit(p);
  assert.ok(a.headRatio>=7.5&&a.headRatio<=8);assert.ok(Math.abs(a.stature-1750)<.1);
  assert.ok(Math.abs(a.shoulderWidth-width)<.1);assert.equal(a.neckLength,40);
  assert.ok(a.symmetry<.6);assert.ok(a.spineLateralDeviation<.05);
 }
});
test('545 mm by 250 mm head targets match actual mesh and survive body-type changes',()=>{
 const p=freshProfile();p.head.dimensions=resizeHeadCircumference([158,250,190],545);
 for(const type of ['neutral','male','female']){p.avatar.type=type;const a=humanAudit(p);assert.ok(Math.abs(a.headCircumference-545)<.01);assert.ok(Math.abs(a.headHeight-250)<.01);}
});
test('explicit torso circumferences match physical horizontal mesh slices',()=>{
 const p=freshProfile();p.chest.details={neck:390,neckBase:420,chestCirc:1020,underBust:960,waist:850,highHip:920,hips:980};
 for(const row of humanGirthAudit(p))assert.ok(Math.abs(row.actual-row.requested)<.1,row.key);
});
test('locked arm segment stays fixed when total changes; two locks reject changes atomically',()=>{
 const p=freshProfile();p.avatar.locks={'armR.upperArmLength':true};
 const value=key=>measurementFields(p,'armR').find(f=>f.key===key).value;
 const before=value('upperArmLength');setMeasurement(p,'armR','total',650);assert.equal(value('upperArmLength'),before);assert.equal(value('total'),650);
 p.avatar.locks['armR.forearmLength']=true;const saved=JSON.stringify(p);assert.throws(()=>setMeasurement(p,'armR','total',700));assert.equal(JSON.stringify(p),saved);
});
test('shape control preserves measured head girth and changes width/depth',()=>{
 const p=freshProfile(),before=bounds(humanScene(p,'head','standing').body).size;
 setMeasurement(p,'head','shape-circ',125);const after=bounds(humanScene(p,'head','standing').body).size;
 assert.ok(after[0]>before[0]);assert.ok(after[2]<before[2]);assert.ok(Math.abs(humanAudit(p).headCircumference-547.79326)<.01);
});
test('kit has a common pivot, uniform scale and round-trips with foam and locks',()=>{
 const mesh=demoShell(),second=mesh.map((v,i)=>v+(i%3===0?240:0));
 const parts=kitParts([{name:'Shell',mesh},{name:'Antenna',mesh:second}],1,'example');
 const separation=bounds(parts[1].mesh).center[0]-bounds(parts[0].mesh).center[0];assert.ok(Math.abs(separation-240)<.01);
 const t=identity();t.scale.fill(1.25);t.offset=[0,12,-5];setKitTransform(parts,parts[0],t);assert.deepEqual(parts[1].transform,t);
 const p=freshProfile();p.head.foamTop=3;p.head.gap=0;p.avatar.locks={'armR.upperArmLength':true};
 const restored=openProject(new TextDecoder().decode(packProject(p,parts,0)));assert.equal(restored.parts[1].group,'example');assert.deepEqual(restored.profile,p);
});
test('top foam increases fitting envelope; uniform fit preserves manual position',()=>{
 const p=freshProfile();p.head.dimensions=resizeHeadCircumference([158,250,190],545);p.head.gap=0;
 const before=humanFittingVolumes(p,'head');const top=v=>Math.max(...v.map(p=>p.center[1]+p.radii[1]));
 p.head.foamTop=3;const after=humanFittingVolumes(p,'head');assert.ok(top(after)>top(before));
 const mesh=demoShell(),quality=inspectMesh(mesh),offset=[0,8,-3];
 const t=autoFit(mesh,'head',p.head.dimensions,0,[0,0,0],quality,'wrap',after,offset);
 assert.deepEqual(t.offset,offset);assert.ok(t.scale.every(v=>v===t.scale[0]));
 assert.equal(evaluate(transform(mesh,t),'head',p.head.dimensions,0,quality,{avatar:after}).collision,false);
});
test('heat map classifies a triangle inside, close to, and away from an envelope',()=>{
 const tri=x=>Float32Array.from([x,-.01,-.01,x,.01,-.01,x,0,.01]);const v=[{center:[0,0,0],radii:[10,10,10]}];
 assert.ok(fitColors(tri(9),v,0)[0]>.9);assert.ok(fitColors(tri(12),v,0)[1]>.7);assert.ok(fitColors(tri(30),v,0)[2]>.9);
});
test('printer split creates closed parts within 245 mm and preserves shell volume',()=>{
 const t=identity();t.scale.fill(2);const mesh=transform(demoShell(),t),pieces=splitForPrinter(mesh,245);
 assert.ok(pieces.length>1);for(const p of pieces){assert.ok(inspectMesh(p).closed);assert.ok(bounds(p).size.every(v=>v<=245.001));}
 const volume=m=>{let sum=0;for(let i=0;i<m.length;i+=9){const [ax,ay,az,bx,by,bz,cx,cy,cz]=m.subarray(i,i+9);sum+=(ax*(by*cz-bz*cy)+ay*(bz*cx-bx*cz)+az*(bx*cy-by*cx))/6;}return sum;};
 const v=volume(mesh);assert.ok(Math.abs(pieces.reduce((s,m)=>s+volume(m),0)-v)/Math.abs(v)<.0001);
 assert.throws(()=>splitForPrinter(Float32Array.from([0,0,0,300,0,0,0,300,0])));
});
