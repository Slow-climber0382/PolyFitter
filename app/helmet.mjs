import {bounds,transform,identity,normalizedDistance} from './geometry.mjs';
export function mergeMeshes(meshes){const merged=new Float32Array(meshes.reduce((n,m)=>n+m.length,0));let offset=0;for(const mesh of meshes){merged.set(mesh,offset);offset+=mesh.length;}return merged;}
export function kitParts(entries,unit=1,id='kit-'+Date.now()){
  const center=bounds(mergeMeshes(entries.map(e=>e.mesh))).center;
  return entries.map(({name,mesh,quality})=>({name,quality,mesh:mesh.map((v,i)=>(v-center[i%3])*unit),region:'head',group:id,transform:identity()}));
}
export function setKitTransform(parts,part,t){
  for(const item of parts)if(item===part||(part.group&&item.group===part.group))item.transform=structuredClone(t);
}
export function kitMesh(parts,part){return mergeMeshes(parts.filter(p=>p===part||(part.group&&p.group===part.group)).map(p=>transform(p.mesh,p.transform)));}
// Triangle colours refer to the conservative fitting envelope, not to pressure.
export function fitColors(mesh,volumes,gap,loose=10){
  const colors=new Float32Array(mesh.length);
  for(let i=0;i<mesh.length;i+=9){
    const face=mesh.subarray(i,i+9);let clearance=Infinity;
    for(const {center,radii} of volumes){
      const d=normalizedDistance(face,radii,center);
      clearance=Math.min(clearance,(d-1)*Math.min(...radii));
      if(clearance<0)break;
    }
    const color=clearance<gap-.05?[.95,.20,.16]:clearance>gap+loose?[.2,.45,.95]:[.2,.8,.42];
    for(let j=0;j<3;j++)colors.set(color,i+j*3);
  }
  return colors;
}
