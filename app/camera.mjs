export function panDelta(dx,dy,yaw,pitch,radius,zoom,width,height){
 const scale=2*radius/(zoom*Math.max(1,Math.min(width,height)));
 const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
 const right=[cy,0,-sy],up=[-sp*sy,cp,-sp*cy];
 return right.map((v,i)=>scale*(-dx*v+dy*up[i]));
}
export const STANDARD_VIEWS={front:[0,0],back:[Math.PI,0],left:[-Math.PI/2,0],right:[Math.PI/2,0],side:[Math.PI/2,0],top:[0,Math.PI/2],bottom:[0,-Math.PI/2]};
