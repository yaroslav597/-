import test from 'node:test';
import assert from 'node:assert/strict';
import {length,optimize,validPoint} from '../src/domain/route.js';
const points=[[0,0],[1,1],[0,1],[1,0]].map(([lat,lng],id)=>({lat,lng,id,alt:80}));
test('known geodesic distance and empty route',()=>{assert.equal(length([]),0);assert.ok(Math.abs(length([{lat:0,lng:0},{lat:0,lng:1}])-111195)<10);});
for(const closed of [false,true]) test(`optimization preserves start and membership, improves crossed route: ${closed}`,()=>{const result=optimize(points,closed);assert.equal(result[0],points[0]);assert.deepEqual(result.map(point=>point.id).sort(),points.map(point=>point.id).sort());assert.ok(length(result,closed)<length(points,closed));assert.equal(points[1].id,1);});
test('degenerate routes and validation',()=>{assert.deepEqual(optimize([]),[]);assert.equal(length([points[0],points[0]],true),0);assert.equal(validPoint({...points[0],lat:91}),false);assert.equal(validPoint({...points[0],alt:NaN}),false);});
