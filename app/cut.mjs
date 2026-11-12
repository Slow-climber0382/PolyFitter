import earcut from './vendor/earcut.mjs';
import {bounds,inspectMesh,cross,sub} from './geometry.mjs';
const EPS=1e-4;
const key=p=>p.map(v=>Math.round(v/EPS)).join(',');
const snap=p=>p.map(v=>Math.round(v/EPS)*EPS);
function loopsFrom(edges){
 const graph=new Map(),points=new Map();
 for(const [a,b] of edges){const ka=key(a),kb=key(b);if(ka===kb)continue;points.set(ka,a);points.set(kb,b);for(const [x,y] of [[ka,kb],[kb,ka]]){if(!graph.has(x))graph.set(x,new Set());graph.get(x).add(y);}}
 if([...graph.values()].some(s=>s.size!==2))throw Error('Przekrój nie tworzy zamkniętych pętli. Zmień orientację lub napraw STL.');
 const loops=[],used=new Set();
 for(const start of graph.keys())if(!used.has(start)){
   const loop=[];let at=start,previous=null;
   do{used.add(at);loop.push(points.get(at));const next=[...graph.get(at)].find(k=>k!==previous);previous=at;at=next;if(loop.length>graph.size)throw Error('Niejednoznaczny przekrój.');}while(at!==start);
   loops.push(loop);
 }
 return loops;
}
function inside(p,poly,axes){let yes=false;const [a,b]=axes;for(let i=0,j=poly.length-1;i<poly.length;j=i++)if((poly[i][b]>p[b])!==(poly[j][b]>p[b])&&p[a]<(poly[j][a]-poly[i][a])*(p[b]-poly[i][b])/(poly[j][b]-poly[i][b])+poly[i][a])yes=!yes;return yes;}
function caps(loops,axis,direction){
 const axes=[(axis+1)%3,(axis+2)%3],result=[];
 const parents=loops.map((loop,i)=>loops.map((other,j)=>j!==i&&inside(loop[0],other,axes)?j:-1).filter(j=>j>=0));
 for(let i=0;i<loops.length;i++)if(parents[i].length%2===0){
  const rings=[loops[i],...loops.filter((_,j)=>parents[j].length===parents[i].length+1&&parents[j].includes(i))];
  const points=rings.flat(),holes=[];let n=rings[0].length;for(const ring of rings.slice(1)){holes.push(n);n+=ring.length;}
  const indices=earcut(points.flatMap(p=>axes.map(a=>p[a])),holes,2);
  let triangles=[];for(let t=0;t<indices.length;t+=3)triangles.push(indices.slice(t,t+3).map(k=>points[k]));
  // Earcut may remove collinear ring vertices. Reinsert them on cap edges,
  // avoiding T-junctions between the cap and the existing shell surface.
  for(const p of points){const next=[];for(const tri of triangles){if(tri.some(q=>key(q)===key(p))){next.push(tri);continue;}let split=false;for(let e=0;e<3;e++){
    const a=tri[e],b=tri[(e+1)%3],c=tri[(e+2)%3],ab=sub(b,a),ap=sub(p,a),length=ab.reduce((s,v)=>s+v*v,0);
    const t=ap.reduce((s,v,k)=>s+v*ab[k],0)/length;
    if(t>1e-7&&t<1-1e-7&&Math.hypot(...ap.map((v,k)=>v-t*ab[k]))<1e-8){next.push([a,p,c],[p,b,c]);split=true;break;}
   }if(!split)next.push(tri);}triangles=next;}
  for(const tri of triangles){if(cross(sub(tri[1],tri[0]),sub(tri[2],tri[0]))[axis]*direction<0)[tri[1],tri[2]]=[tri[2],tri[1]];result.push(...tri.flat());}
 }
 return result;
}
export function cutPlane(mesh,axis,level){
 const halves=[[],[]],edges=[];
 for(let i=0;i<mesh.length;i+=9){
   const tri=[0,3,6].map(j=>snap(Array.from(mesh.subarray(i+j,i+j+3))));
   const hits=[];
   for(let e=0;e<3;e++){const a=tri[e],b=tri[(e+1)%3],av=a[axis]-level,bv=b[axis]-level;if((av<0)!==(bv<0)){const t=av/(av-bv),p=snap(a.map((v,k)=>v+t*(b[k]-v)));p[axis]=level;hits.push(p);}}
   if(hits.length===2)edges.push(hits);
   for(let side=0;side<2;side++){
     const output=[];
     for(let e=0;e<3;e++){const a=tri[e],b=tri[(e+1)%3],av=a[axis]-level,bv=b[axis]-level;const ina=side?av>=0:av<=0,inb=side?bv>=0:bv<=0;
       if(ina)output.push(a);if(ina!==inb){const t=av/(av-bv),p=snap(a.map((v,k)=>v+t*(b[k]-v)));p[axis]=level;output.push(p);}
     }
     for(let j=1;j+1<output.length;j++)if(Math.hypot(...cross(sub(output[j],output[0]),sub(output[j+1],output[0])))>1e-8)halves[side].push(...output[0],...output[j],...output[j+1]);
   }
 }
 const loops=loopsFrom(edges);
 for(let side=0;side<2;side++)halves[side].push(...caps(loops,axis,side?-1:1));
 return halves.filter(a=>a.length).map(a=>Float32Array.from(a));
}
export function splitForPrinter(mesh,limit=245){
 const limits=typeof limit==='number'?[limit,limit,limit]:limit;
 if(!Array.isArray(limits)||limits.length!==3||limits.some(v=>!Number.isFinite(v)||v<=0))throw Error('Wymiary obszaru druku muszą być dodatnimi, skończonymi liczbami.');
 if(!inspectMesh(mesh).closed)throw Error('Podział wymaga zamkniętej siatki bez zdegenerowanych trójkątów. Napraw STL przed cięciem.');
 const queue=[mesh],result=[];
 while(queue.length){
  const part=queue.shift(),b=bounds(part),ratios=b.size.map((v,i)=>v/limits[i]),axis=ratios.indexOf(Math.max(...ratios));
  if(b.size.every((v,i)=>v<=limits[i]+.001)){result.push(part);continue;}
  if(result.length+queue.length>=63)throw Error('Za dużo części. Sprawdź skalę modelu.');
  // A tiny shift avoids planes passing exactly through common mesh vertices.
  const level=Math.round((b.center[axis]+.0137)*1e4)/1e4;
  const split=cutPlane(part,axis,level);
  if(split.length!==2)throw Error('Nie udało się przeciąć modelu.');
  for(const piece of split)if(!inspectMesh(piece).closed)throw Error('Cięcie nie przeszło kontroli szczelności. Nie wyeksportowano wadliwych części.');
  queue.push(...split);
 }
 return result;
}
