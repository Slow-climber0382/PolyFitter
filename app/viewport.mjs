import {panDelta,STANDARD_VIEWS} from './camera.mjs';
import { bounds, cross, sub } from './geometry.mjs';

const vertex = `attribute vec3 position;
attribute vec3 normal;
attribute vec3 color;
varying vec3 tint;
uniform mat3 camera;
uniform vec3 focus;
uniform vec3 projection;
varying vec3 world;
varying vec3 view;
varying vec3 viewNormal;
void main(){
  tint=color;
  world=position;
  view=camera*(position-focus);
  viewNormal=camera*normal;
  gl_Position=vec4(view*projection,1.0);
}`;
const fragment = `#extension GL_OES_standard_derivatives : enable
precision highp float;
uniform vec4 paint;
uniform bool heatmap;
varying vec3 tint;
uniform bool shaded;
uniform bool useNormals;
uniform bool section;
varying vec3 world;
varying vec3 view;
varying vec3 viewNormal;
void main(){
  if(section && world.z>0.0) discard;
  vec3 direction=useNormals ? normalize(viewNormal) : normalize(cross(dFdx(view),dFdy(view)));
  float light=shaded ? 0.33+0.67*abs(dot(direction,normalize(vec3(-0.35,0.65,-1.0)))) : 1.0;
  gl_FragColor=vec4((heatmap?tint:paint.rgb)*light,paint.a);
}`;
function program(gl){
  const compiled=gl.createProgram();
  for(const [type,source] of [[gl.VERTEX_SHADER,vertex],[gl.FRAGMENT_SHADER,fragment]]){
    const shader=gl.createShader(type);
    gl.shaderSource(shader,source);gl.compileShader(shader);
    if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(shader));
    gl.attachShader(compiled,shader);gl.deleteShader(shader);
  }
  gl.linkProgram(compiled);
  if(!gl.getProgramParameter(compiled,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(compiled));
  return compiled;
}
function smoothNormals(vertices){
  const sums=new Map(),keys=[];
  for(let i=0;i<vertices.length;i+=9){
    const a=vertices.subarray(i,i+3),b=vertices.subarray(i+3,i+6),c=vertices.subarray(i+6,i+9);
    const n=cross(sub(b,a),sub(c,a));
    for(const p of [a,b,c]){
      const key=p.join(',');
      const sum=sums.get(key)??[0,0,0];
      for(let axis=0;axis<3;axis++)sum[axis]+=n[axis];
      sums.set(key,sum);keys.push(key);
    }
  }
  const result=new Float32Array(vertices.length);
  for(let i=0;i<keys.length;i++)result.set(sums.get(keys[i]),i*3);
  return result;
}
export function createViewport(canvas){
  const gl=canvas.getContext('webgl',{antialias:true});
  if(!gl||!gl.getExtension('OES_standard_derivatives'))throw Error('Widok 3D wymaga działającego WebGL.');
  const pipeline=program(gl);
  gl.useProgram(pipeline);
  const uniforms=Object.fromEntries(['camera','focus','projection','paint','shaded','section','useNormals','heatmap'].map(name=>[name,gl.getUniformLocation(pipeline,name)]));
  const attribute=gl.getAttribLocation(pipeline,'position');
  const normalAttribute=gl.getAttribLocation(pipeline,'normal');
  const normalBuffer=gl.createBuffer(), colorBuffer=gl.createBuffer(), colorAttribute=gl.getAttribLocation(pipeline,'color');
  let hasColors=false;
  gl.enableVertexAttribArray(attribute);
  gl.enable(gl.DEPTH_TEST);gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
  const buffers=Object.fromEntries(['mesh','body','grid','seams'].map(key=>[key,{id:gl.createBuffer(),count:0}]));
  let yaw=-0.51,pitch=0.16,zoom=1,radius=160,cut=false,xray=false,showBody=true,pointer=null;
  let focus=[0,0,0],pan=[0,0,0],lastBody=null,allBounds=null,selectedBounds=null;
  function upload(name,data){
    const buffer=buffers[name];
    gl.bindBuffer(gl.ARRAY_BUFFER,buffer.id);gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);
    buffer.count=data.length/3;
  }
  function drawBuffer(name,mode,paint,shaded=false,section=false){
    const buffer=buffers[name];
    gl.bindBuffer(gl.ARRAY_BUFFER,buffer.id);gl.vertexAttribPointer(attribute,3,gl.FLOAT,false,0,0);
    gl.uniform1i(uniforms.heatmap,+(name==='mesh'&&hasColors));
    if(name==='mesh'&&hasColors){gl.bindBuffer(gl.ARRAY_BUFFER,colorBuffer);gl.enableVertexAttribArray(colorAttribute);gl.vertexAttribPointer(colorAttribute,3,gl.FLOAT,false,0,0);}
    else{gl.disableVertexAttribArray(colorAttribute);gl.vertexAttrib3f(colorAttribute,1,1,1);}
    const smooth=name==='body';
    gl.uniform1i(uniforms.useNormals,+smooth);
    if(smooth){
      gl.bindBuffer(gl.ARRAY_BUFFER,normalBuffer);gl.enableVertexAttribArray(normalAttribute);
      gl.vertexAttribPointer(normalAttribute,3,gl.FLOAT,false,0,0);
    }else{
      gl.disableVertexAttribArray(normalAttribute);
      gl.vertexAttrib3f(normalAttribute,0,0,0);
    }
    gl.uniform4fv(uniforms.paint,paint);gl.uniform1i(uniforms.shaded,+shaded);gl.uniform1i(uniforms.section,+section);
    gl.drawArrays(mode,0,buffer.count);
  }
  let pending=false;
  function draw(){
    if(pending)return;
    pending=true;
    requestAnimationFrame(()=>{
      pending=false;
      const ratio=Math.min(window.devicePixelRatio||1,2);
      const w=Math.max(1,Math.round(canvas.clientWidth*ratio)), h=Math.max(1,Math.round(canvas.clientHeight*ratio));
      if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
      gl.viewport(0,0,w,h);gl.clearColor(.074,.087,.118,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
      const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
      gl.uniformMatrix3fv(uniforms.camera,false,new Float32Array([cy,-sp*sy,cp*sy,0,cp,sp,-sy,-sp*cy,cp*cy]));
      gl.uniform3fv(uniforms.focus,focus.map((v,i)=>v+pan[i]));
      const length=radius/zoom;
      gl.uniform3fv(uniforms.projection,[Math.min(1,h/w)/length,Math.min(1,w/h)/length,-1/(radius*12)]);
      drawBuffer('grid',gl.LINES,[.28,.34,.43,.44]);
      if(showBody){
        gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(1,1);
        drawBuffer('body',gl.TRIANGLES,[.72,.73,.74,1],true);
        gl.disable(gl.POLYGON_OFFSET_FILL);
        drawBuffer('seams',gl.LINES,[.065,.067,.07,1]);
      }
      if(xray){gl.depthMask(false);gl.disable(gl.DEPTH_TEST);}
      drawBuffer('mesh',gl.TRIANGLES,[.54,.69,.93,xray?.19:1],true,cut);
      if(xray){gl.enable(gl.DEPTH_TEST);gl.depthMask(true);}
    });
  }
  new ResizeObserver(draw).observe(canvas);
  canvas.addEventListener('contextmenu',e=>e.preventDefault());
  canvas.addEventListener('pointerdown',e=>{if(e.button!==0&&e.button!==2)return;e.preventDefault();pointer=[e.clientX,e.clientY,e.button];canvas.setPointerCapture(e.pointerId);});
  canvas.addEventListener('pointermove',e=>{
    if(!pointer)return;
    const dx=e.clientX-pointer[0],dy=e.clientY-pointer[1],button=pointer[2];
    if(button===0){yaw+=dx*.009;pitch=Math.max(-1.55,Math.min(1.55,pitch+dy*.009));}
    else{const delta=panDelta(dx,dy,yaw,pitch,radius,zoom,canvas.clientWidth,canvas.clientHeight);pan=pan.map((v,i)=>v+delta[i]);}
    pointer=[e.clientX,e.clientY,button];draw();
  });
  for(const type of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(type,()=>pointer=null);
  canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.min(6,Math.max(.3,zoom*Math.exp(-e.deltaY*.0012)));draw();},{passive:false});
  canvas.addEventListener('keydown',e=>{
    if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','-'].includes(e.key))return;
    e.preventDefault();
    if(e.key==='ArrowLeft')yaw-=.13;if(e.key==='ArrowRight')yaw+=.13;
    if(e.key==='ArrowUp')pitch=Math.max(-1.55,pitch-.13);if(e.key==='ArrowDown')pitch=Math.min(1.55,pitch+.13);
    if(e.key==='+')zoom=Math.min(6,zoom*1.12);if(e.key==='-')zoom=Math.max(.3,zoom/1.12);draw();
  });
  return {
    scene(mesh,bodyMesh,focusMesh=bodyMesh,seams=new Float32Array(),colors=null){
      hasColors=!!colors;if(colors){gl.bindBuffer(gl.ARRAY_BUFFER,colorBuffer);gl.bufferData(gl.ARRAY_BUFFER,colors,gl.STATIC_DRAW);}
      upload('seams',seams);
      upload('mesh',mesh||new Float32Array());
      if(bodyMesh!==lastBody){
        upload('body',bodyMesh);
        gl.bindBuffer(gl.ARRAY_BUFFER,normalBuffer);
        gl.bufferData(gl.ARRAY_BUFFER,smoothNormals(bodyMesh),gl.STATIC_DRAW);
        lastBody=bodyMesh;
      }
      const body=bounds(focusMesh), limits=mesh?bounds(mesh):body;
      const whole=bounds(bodyMesh);allBounds={min:whole.min.map((v,i)=>Math.min(v,limits.min[i])),max:whole.max.map((v,i)=>Math.max(v,limits.max[i]))};
      selectedBounds=mesh?bounds(mesh):body;
      const min=body.min.map((v,i)=>Math.min(v,limits.min[i]));
      const max=body.max.map((v,i)=>Math.max(v,limits.max[i]));
      focus=min.map((v,i)=>(v+max[i])/2);
      radius=.65*Math.max(...max.map((v,i)=>v-min[i]),1);
      const spacing=Math.pow(10,Math.floor(Math.log10(radius/4)));
      const level=bounds(bodyMesh).min[1]-4, extent=spacing*12, grid=[];
      for(let i=-12;i<=12;i++)grid.push(i*spacing,level,-extent,i*spacing,level,extent,-extent,level,i*spacing,extent,level,i*spacing);
      upload('grid',new Float32Array(grid));draw();
    },
    view(mode){
      if(STANDARD_VIEWS[mode]){[yaw,pitch]=STANDARD_VIEWS[mode];pan=[0,0,0];}
      if(mode==='reset'){yaw=-.51;pitch=.26;zoom=1;pan=[0,0,0];}
      if(mode==='all'||mode==='selected'){const box=mode==='all'?allBounds:selectedBounds;if(box){focus=box.min.map((v,i)=>(v+box.max[i])/2);radius=.65*Math.max(...box.max.map((v,i)=>v-box.min[i]),1);zoom=1;pan=[0,0,0];}}
      if(mode==='section'){cut=!cut;if(cut){yaw=Math.PI/4;pitch=.15;}}
      if(mode==='xray')xray=!xray;
      if(mode==='body')showBody=!showBody;
      draw();
    }
  };
}
