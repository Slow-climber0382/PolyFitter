export const MAX_FACES = 1000000;
export const identity = () => ({scale:[1,1,1], rotate:[0,0,0], offset:[0,0,0]});
export const sub = (a,b) => a.map((x,i)=>x-b[i]);
export const dot = (a,b) => a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
export const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const addScaled = (a,b,t) => a.map((x,i)=>x+b[i]*t);
export function bounds(vertices) {
  const min=[Infinity,Infinity,Infinity], max=[-Infinity,-Infinity,-Infinity];
  for(let i=0;i<vertices.length;i++){const axis=i%3;min[axis]=Math.min(min[axis],vertices[i]);max[axis]=Math.max(max[axis],vertices[i]);}
  return {min,max,size:sub(max,min),center:min.map((x,i)=>(x+max[i])/2)};
}
export function parseSTL(buffer) {
  const view=new DataView(buffer);
  const n=buffer.byteLength>=84?view.getUint32(80,true):0;
  let mesh;
  if(n && 84+n*50===buffer.byteLength){
    if(n>MAX_FACES) throw Error('Limit to 1 000 000 trójkątów.');
    mesh=new Float32Array(n*9);
    for(let f=0;f<n;f++)for(let j=0;j<9;j++)mesh[f*9+j]=view.getFloat32(96+f*50+j*4,true);
  } else {
    const source=new TextDecoder().decode(buffer).trim();
    if(!/^solid\b/i.test(source)||!/\bendsolid\b/i.test(source))throw Error('Nie rozpoznano poprawnego pliku STL.');
    const matches=source.matchAll(/\bvertex\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)/gi);
    const values=[];
    for(const m of matches){
      const coordinates=m.slice(1).map(Number);
      if(coordinates.some(x=>!Number.isFinite(x)))throw Error('Nieprawidłowa współrzędna STL.');
      values.push(...coordinates);
      if(values.length>MAX_FACES*9)throw Error('Limit to 1 000 000 trójkątów.');
    }
    if(!values.length || values.length%9)throw Error('Niepełne trójkąty STL.');
    mesh=Float32Array.from(values);
  }
  if(mesh.some(x=>!Number.isFinite(x)))throw Error('Model zawiera nieprawidłowe współrzędne.');
  if(!bounds(mesh).size.some(x=>x>0))throw Error('Model nie ma wymiarów.');
  return mesh;
}
export function transform(vertices,t) {
  const [x,y,z]=t.rotate.map(d=>d*Math.PI/180);
  const [cx,cy,cz]=[Math.cos(x),Math.cos(y),Math.cos(z)], [sx,sy,sz]=[Math.sin(x),Math.sin(y),Math.sin(z)];
  const result=new Float32Array(vertices.length);
  for(let i=0;i<vertices.length;i+=3){
    const a=vertices[i]*t.scale[0], b=vertices[i+1]*t.scale[1], c=vertices[i+2]*t.scale[2];
    const v=b*cx-c*sx, w=b*sx+c*cx;
    const u=a*cy+w*sy, q=-a*sy+w*cy;
    result[i]=u*cz-v*sz+t.offset[0];
    result[i+1]=u*sz+v*cz+t.offset[1];
    result[i+2]=q+t.offset[2];
  }
  return result;
}
export function centerMesh(mesh, unit=1) {
  const {center}=bounds(mesh);
  return mesh.map((x,i)=>(x-center[i%3])*unit);
}
export function writeSTL(mesh){
  const file=new ArrayBuffer(84+mesh.length/9*50), view=new DataView(file);
  new Uint8Array(file).set(new TextEncoder().encode('Meshavon | millimetres'));
  view.setUint32(80,mesh.length/9,true);
  for(let i=0;i<mesh.length;i+=9){
    const a=mesh.subarray(i,i+3),b=mesh.subarray(i+3,i+6),c=mesh.subarray(i+6,i+9);
    const n=cross(sub(b,a),sub(c,a)), length=Math.hypot(...n)||1, offset=84+i/9*50;
    for(let j=0;j<3;j++)view.setFloat32(offset+j*4,n[j]/length,true);
    for(let j=0;j<9;j++)view.setFloat32(offset+12+j*4,mesh[i+j],true);
  }
  return file;
}
function segmentDistance(a,b){
  const ab=sub(b,a), length=dot(ab,ab);
  const p=addScaled(a,ab,length?Math.max(0,Math.min(1,-dot(a,ab)/length)):0);
  return dot(p,p);
}
// Closest squared distance to the origin. Use the plane projection when
// inside the triangle, otherwise the closest point lies on an edge.
export function triangleDistance(a,b,c) {
  const ab=sub(b,a), ac=sub(c,a), n=cross(ab,ac), norm=dot(n,n);
  if(norm>1e-24){
    const h=dot(a,n), p=n.map(x=>x*h/norm);
    if(dot(cross(ab,sub(p,a)),n)>=0 && dot(cross(sub(c,b),sub(p,b)),n)>=0 && dot(cross(sub(a,c),sub(p,c)),n)>=0)return h*h/norm;
  }
  return Math.min(segmentDistance(a,b),segmentDistance(b,c),segmentDistance(c,a));
}
// The tree is reused for all mannequin volumes and trial positions.
function triangleIndex(mesh){
  if(mesh.length<18000)return null;
  const offsets=Array.from({length:mesh.length/9},(_,i)=>i*9);
  const centers=new Float32Array(offsets.length*3);
  for(const i of offsets)for(let axis=0;axis<3;axis++)
    centers[i/3+axis]=(mesh[i+axis]+mesh[i+3+axis]+mesh[i+6+axis])/3;
  function build(from,to,depth=0){
    const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
    for(let j=from;j<to;j++){
      const offset=offsets[j];
      for(let k=0;k<9;k++){
        const axis=k%3, value=mesh[offset+k];
        min[axis]=Math.min(min[axis],value);max[axis]=Math.max(max[axis],value);
      }
    }
    const node={min,max,from,to};
    if(to-from<=32||depth>=32)return node;
    const sizes=sub(max,min),axis=sizes.indexOf(Math.max(...sizes));
    const pivot=(min[axis]+max[axis])/2;
    let low=from,high=to-1;
    while(low<=high){
      if(centers[offsets[low]/3+axis]<pivot)low++;
      else {[offsets[low],offsets[high]]=[offsets[high],offsets[low]];high--;}
    }
    if(low===from||low===to)low=Math.floor((from+to)/2);
    node.left=build(from,low,depth+1);node.right=build(low,to,depth+1);
    return node;
  }
  return {offsets,root:build(0,offsets.length)};
}

export function normalizedDistance(mesh,radii,center=[0,0,0],index=null,threshold=0){
  let nearest=Infinity;
  const points=Array.from({length:3},()=>[0,0,0]);
  function triangle(i){
    let bound=0;
    for(let axis=0;axis<3;axis++){
      for(let j=0;j<3;j++)points[j][axis]=(mesh[i+j*3+axis]-center[axis])/radii[axis];
      const lo=Math.min(points[0][axis],points[1][axis],points[2][axis]), hi=Math.max(points[0][axis],points[1][axis],points[2][axis]);
      bound+=(lo>0?lo:hi<0?hi:0)**2;
    }
    if(bound<nearest)nearest=Math.min(nearest,triangleDistance(...points));
  }
  const boxDistance=({min,max})=>{
    let distance=0;
    for(let i=0;i<3;i++)distance+=(Math.max(0,min[i]-center[i],center[i]-max[i])/radii[i])**2;
    return distance;
  };
  function visit(node,lower){
    if(lower>=nearest||nearest<threshold)return;
    if(node.left){
      const a=boxDistance(node.left), b=boxDistance(node.right);
      if(a<b){visit(node.left,a);visit(node.right,b);}
      else{visit(node.right,b);visit(node.left,a);}
    }else{
      for(let j=node.from;j<node.to&&nearest>=threshold;j++)triangle(index.offsets[j]);
    }
  }
  if(index)visit(index.root,boxDistance(index.root));
  else for(let i=0;i<mesh.length&&nearest>=threshold;i+=9)triangle(i);
  return Math.sqrt(nearest);
}
export function inspectMesh(mesh){
  // Compact numeric edge keys avoid storing millions of long coordinate pairs.
  const vertices=new Map(),edges=new Float64Array(mesh.length/3),parents=new Int32Array(mesh.length/3);
  const radix=mesh.length/3+1;let next=0,components=0,degenerate=0;
  function root(a){while(parents[a]!==a){parents[a]=parents[parents[a]];a=parents[a];}return a;}
  function join(a,b){a=root(a);b=root(b);if(a!==b){parents[b]=a;components--;}}
  const ids=[0,0,0];
  for(let i=0;i<mesh.length;i+=9){
    for(let j=0;j<3;j++){
      const k=i+j*3,key=mesh[k]+','+mesh[k+1]+','+mesh[k+2];
      let id=vertices.get(key);if(id===undefined){id=next++;vertices.set(key,id);parents[id]=id;components++;}ids[j]=id;
    }
    join(ids[0],ids[1]);join(ids[1],ids[2]);
    const ux=mesh[i+3]-mesh[i],uy=mesh[i+4]-mesh[i+1],uz=mesh[i+5]-mesh[i+2];
    const vx=mesh[i+6]-mesh[i],vy=mesh[i+7]-mesh[i+1],vz=mesh[i+8]-mesh[i+2];
    if(Math.hypot(uy*vz-uz*vy,uz*vx-ux*vz,ux*vy-uy*vx)<1e-12)degenerate++;
    for(let j=0;j<3;j++){const a=ids[j],b=ids[(j+1)%3];edges[i/3+j]=Math.min(a,b)*radix+Math.max(a,b);}
  }
  edges.sort();let boundary=0,nonManifold=0;
  for(let start=0;start<edges.length;){let end=start+1;while(end<edges.length&&edges[end]===edges[start])end++;const count=end-start;if(count===1)boundary++;else if(count>2)nonManifold++;start=end;}
  return {faces:mesh.length/9,vertices:next,components,degenerate,boundary,nonManifold,closed:!boundary&&!nonManifold&&!degenerate};
}
function insideSolid(mesh){
  const d=[1,0.37235,0.19293], hits=[];
  for(let i=0;i<mesh.length;i+=9){
    const a=mesh.subarray(i,i+3), b=mesh.subarray(i+3,i+6), c=mesh.subarray(i+6,i+9);
    const e=sub(b,a), f=sub(c,a), p=cross(d,f), determinant=dot(e,p);
    if(Math.abs(determinant)<1e-10)continue;
    const o=a.map(x=>-x), u=dot(o,p)/determinant;
    if(u<0||u>1)continue;
    const q=cross(o,e), v=dot(d,q)/determinant, t=dot(f,q)/determinant;
    if(v>=0&&u+v<=1&&t>1e-8)hits.push(t);
  }
  hits.sort((a,b)=>a-b);
  return hits.filter((t,i)=>i===0||Math.abs(t-hits[i-1])>1e-6).length%2===1;
}
function padded(radii,gap){
  if(!gap)return radii;
  // This ellipsoid contains the Minkowski sum with a gap-radius sphere.
  // It stays tight even for a thin ellipsoid around a skin patch.
  const ratio=gap/Math.sqrt(Math.min(...radii)*Math.max(...radii));
  return radii.map(r=>Math.sqrt((1+ratio)*r*r+(1+1/ratio)*gap*gap));
}
const bodyVolumes=(dimensions,avatar)=>avatar??[{center:[0,0,0],radii:dimensions.map(x=>x/2)}];
const paddedVolumes=(volumes,gap)=>volumes.map(({center,radii})=>({center,radii:padded(radii,gap)}));

function clears(mesh,index,volumes,scale=1,offset=[0,0,0]){
  return volumes.every(({center,radii})=>normalizedDistance(mesh,
    radii.map(x=>x/scale),center.map((x,i)=>(x-offset[i])/scale),index,1)>=1);
}

export function autoFit(mesh, region, dimensions, gap, rotate, quality, shinStyle = 'wrap', avatar, offset=[0,0,0], searchPlacement=false) {
  const target=paddedVolumes(bodyVolumes(dimensions,avatar),gap);
  const t=identity();t.rotate=[...rotate];t.offset=[...offset];
  const oriented=transform(mesh,{...t,offset:[0,0,0]}), box=bounds(oriented), index=triangleIndex(oriented);
  const frontPlate=region==='chest'||(region==='shin'&&shinStyle==='front');
  if(frontPlate){
    if(box.size[0]<0.01||box.size[1]<0.01)throw Error('Ustaw przód płyty w kierunku +Z, a jej wysokość wzdłuż osi Y.');
    const scale=Math.max(dimensions[0]/box.size[0],dimensions[1]/box.size[1]);
    t.scale.fill(scale);
    const front=Math.max(...target.map(({center,radii})=>center[2]+radii[2]));
    const start=front-box.min[2]*scale+0.1;
    const minimum=front*0.25-(box.min[2]+box.max[2])*scale/2;
    const valid=z=>clears(oriented,index,target,scale,[offset[0],offset[1],z]);
    let good=start,bad=null;
    for(let step=1;step<=12;step++){
      const trial=start+(minimum-start)*step/12;
      if(!valid(trial)){bad=trial;break;}good=trial;
    }
    if(bad!==null)for(let step=0;step<12;step++){
      const trial=(good+bad)/2;if(valid(trial))good=trial;else bad=trial;
    }
    t.offset[2]=good;
  }else{
    if(quality.closed&&insideSolid(oriented))throw Error('Środek modelu wypada w materiale. Wybierz wydrążony element lub skoryguj ustawienie ręcznie.');
    if(!avatar){
      const distance=normalizedDistance(oriented,target[0].radii);
      if(distance<0.03)throw Error('Środek bryły jest za blisko ścianki. Wyrównaj model lub użyj ręcznej korekty.');
      t.scale.fill(1.001/distance);
    }else{
      // Test placement from small to large and refine the first sampled
      // interval with clearance. A non-convex shell may have other intervals.
      let low=0.005, high=Math.max(low,Math.min(50,.50*Math.min(
        ...dimensions.map((x,i)=>x/Math.max(0.01,box.size[i]))
      )));
      while(!clears(oriented,index,target,high,offset)){
        if(high>=50)throw Error('Nie znaleziono skali z wymaganym luzem. Sprawdź orientację i wnętrze modelu.');
        low=high;high=Math.min(50,high*1.4);
      }
      for(let step=0;step<16;step++){
        const trial=(low+high)/2;
        if(clears(oriented,index,target,trial,offset))high=trial;else low=trial;
      }
      const suggested=Math.min(50,high*1.0001);
      t.scale.fill(clears(oriented,index,target,suggested,offset)?suggested:high);
    }
  }
  if(searchPlacement&&region==='head'&&avatar){
    const lower=[0,1,2].map(i=>Math.min(...target.map(v=>v.center[i]-v.radii[i])));
    const upper=[0,1,2].map(i=>Math.max(...target.map(v=>v.center[i]+v.radii[i])));
    const contained=(s,o)=>lower.every((v,i)=>box.min[i]*s+o[i]<=v+.1&&box.max[i]*s+o[i]>=upper[i]-.1);
    let best=t.scale[0],bestOffset=[...offset];
    const solve=o=>{
      if(!contained(best,o)||!clears(oriented,index,target,best,o))return;
      let lo=.005,hi=best;
      for(let n=0;n<12;n++){const mid=(lo+hi)/2;if(contained(mid,o)&&clears(oriented,index,target,mid,o))hi=mid;else lo=mid;}
      if(hi<best-1e-5){best=hi;bestOffset=o;}
    };
    for(const step of [20,5]){
      const origin=[...bestOffset];
      const extent=step===20?3:2;
      for(let y=-extent;y<=extent;y++)for(let z=-extent;z<=extent;z++)solve([origin[0],origin[1]+y*step,origin[2]+z*step]);
    }
    t.scale.fill(best*1.0001);t.offset=bestOffset;
  }
  if(region==='shin'&&box.size[1]*t.scale[1]>dimensions[1]*1.6)
    throw Error('Proponowana goleń byłaby ponad 60% wyższa od obszaru ciała. Nie zastosowano wyniku. Sprawdź orientację, położenie i zakres ochraniacza.');
  if(t.scale.some(s=>!Number.isFinite(s)||s<0.005||s>50))throw Error('Nietypowa skala. Sprawdź jednostki STL i wymiary.');
  return t;
}
export function evaluate(mesh,region,dimensions,gap,quality,{entry=false,avatar}={}){
  const volumes=bodyVolumes(dimensions,avatar),index=triangleIndex(mesh);
  let margin=Infinity;
  for(const {radii,center} of volumes){
    const d=normalizedDistance(mesh,radii,center,index,0.9999**2);
    if(d<0.9999){margin=null;break;}
    margin=Math.min(margin,Math.max(0,d-1)*Math.min(...radii));
  }
  const solid=margin!==null&&quality.closed&&insideSolid(mesh);
  if(!solid&&margin!==null&&margin<gap&&clears(mesh,index,paddedVolumes(volumes,gap)))margin=gap;
  const result={collision:margin===null||solid,solid,margin:solid?null:margin,entry:null};
  if(region==='head'&&entry&&!result.collision){
    const target=paddedVolumes(volumes,gap);
    const top=Math.max(...target.map(({center,radii})=>center[1]+radii[1]));
    const limit=Math.min(bounds(mesh).min[1]-top-1,-1);
    const stepCount=Math.ceil(-limit/Math.max(2,Math.min(...dimensions)/16));
    if(stepCount>64){result.entry='unknown';return result;}
    result.entry='clear';
    for(let j=0;j<=stepCount;j++){
      if(!clears(mesh,index,target,1,[0,-limit*j/stepCount,0])){
        result.entry='blocked';break;
      }
    }
  }
  return result;
}

export function demoShell(){
  // Hollow, bottom-open shell with a lip, generated for the built-in example.
  const n=32,m=14, vertices=[];
  const ring=(j,i,inner)=>{
    const latitude=-0.82+(Math.PI/2+0.82)*j/m, theta=2*Math.PI*(i%n)/n;
    const r=inner?[88,111,105]:[96,119,113];
    if(j===m)return [0,r[1],0];
    return [r[0]*Math.cos(latitude)*Math.cos(theta),r[1]*Math.sin(latitude),r[2]*Math.cos(latitude)*Math.sin(theta)];
  };
  const triangle=(...points)=>vertices.push(...points.flat());
  for(let j=0;j<m;j++)for(let i=0;i<n;i++){
    for(const inner of [false,true]){
      const a=ring(j,i,inner),b=ring(j,i+1,inner),c=ring(j+1,i,inner);
      if(inner)triangle(a,b,c);else triangle(a,c,b);
      if(j<m-1){const d=ring(j+1,i+1,inner);if(inner)triangle(b,d,c);else triangle(b,c,d);}
    }
    if(j===0){
      const a=ring(0,i,false),b=ring(0,i+1,false),c=ring(0,i,true),d=ring(0,i+1,true);
      triangle(a,b,c);triangle(b,d,c);
    }
  }
  return Float32Array.from(vertices);
}
