import test from 'node:test';
import assert from 'node:assert/strict';
import {length,validPoint} from '../src/domain/route.js';
const points=[[0,0],[1,1],[0,1],[1,0]].map(([lat,lng],id)=>({lat,lng,id,alt:80}));
test('known geodesic distance and empty route',()=>{assert.equal(length([]),0);assert.ok(Math.abs(length([{lat:0,lng:0},{lat:0,lng:1}])-111195)<10);});
test('degenerate routes and validation',()=>{assert.equal(length([points[0],points[0]],true),0);assert.equal(validPoint({...points[0],lat:91}),false);assert.equal(validPoint({...points[0],alt:NaN}),false);});
