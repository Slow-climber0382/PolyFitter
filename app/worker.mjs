export function geometryTask(job,buffer,args){
 return new Promise((resolve,reject)=>{
  const worker=new Worker(new URL('./mesh-worker.mjs',import.meta.url),{type:'module'});
  worker.onmessage=({data})=>{worker.terminate();if(data.error)reject(Error(data.error));else resolve(data);};
  worker.onerror=event=>{worker.terminate();reject(Error(event.message||'Nie udało się przetworzyć geometrii.'));};
  worker.postMessage({job,buffer,args},[buffer]);
 });
}
