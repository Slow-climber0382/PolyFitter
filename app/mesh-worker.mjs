import {fitColors} from './helmet.mjs';
import {parseSTL,inspectMesh,autoFit} from './geometry.mjs';
self.onmessage=({data})=>{
 try{
  if(data.job==='parse'){
   const mesh=parseSTL(data.buffer),quality=inspectMesh(mesh);
   self.postMessage({mesh:mesh.buffer,quality},[mesh.buffer]);
  }else if(data.job==='colors'){
   const colors=fitColors(new Float32Array(data.buffer),...data.args);self.postMessage({colors:colors.buffer},[colors.buffer]);
  }else if(data.job==='fit'){
   const result=autoFit(new Float32Array(data.buffer),...data.args);self.postMessage({result});
  }else throw Error('Nieznana operacja geometrii.');
 }catch(error){self.postMessage({error:error.message});}
};
