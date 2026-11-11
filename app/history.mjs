// Meshes are immutable; snapshots share them instead of copying millions of vertices.
export function snapshot(state){return {...state,profile:structuredClone(state.profile),parts:state.parts.map(p=>({...p,transform:structuredClone(p.transform)}))};}
export function createHistory(initial,limit=40){
 let past=[],present=snapshot(initial),future=[];
 return {
 commit(state){past.push(present);if(past.length>limit)past.shift();present=snapshot(state);future=[];},
 reset(state){past=[];future=[];present=snapshot(state);},
 undo(){if(!past.length)return null;future.push(present);present=past.pop();return snapshot(present);},
 redo(){if(!future.length)return null;past.push(present);present=future.pop();return snapshot(present);},
 get canUndo(){return past.length>0;},get canRedo(){return future.length>0;}
 };
}
