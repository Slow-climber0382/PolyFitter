import test from 'node:test';import assert from 'node:assert/strict';import {panDelta,STANDARD_VIEWS} from '../app/camera.mjs';
test('pan follows screen plane at front and side without changing depth',()=>{
 assert.deepEqual(panDelta(10,0,0,0,100,1,200,200),[-10,0,0]);
 const side=panDelta(10,0,Math.PI/2,0,100,1,200,200);assert.ok(Math.abs(side[0])<1e-10);assert.equal(side[2],10);
 assert.deepEqual(panDelta(0,10,0,0,100,2,200,200).map(v=>v||0),[0,5,0]);
});
test('six orthogonal views expose both poles and opposite directions',()=>{
 assert.equal(STANDARD_VIEWS.back[0]-STANDARD_VIEWS.front[0],Math.PI);
 assert.equal(STANDARD_VIEWS.right[0]-STANDARD_VIEWS.left[0],Math.PI);
 assert.equal(STANDARD_VIEWS.top[1]-STANDARD_VIEWS.bottom[1],Math.PI);
});
