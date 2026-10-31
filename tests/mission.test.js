import test from 'node:test';
import assert from 'node:assert/strict';
import {commands,defaults,normalizePoint,normalizeSettings,missionItem,buildMission,restoreMission,flightPath,missionWarnings} from '../src/domain/mission.js';
import {simulationSteps,simulationFrame} from '../src/domain/simulation.js';
const point=(changes={})=>normalizePoint({id:'a',lat:55.755,lng:37.59,alt:80,...changes});
const action=(command,params=defaults(command),other={})=>({id:`action-${command}`,command,params,...other});

test('all ten numeric commands export with correct MAVLink parameter positions',()=>{
  assert.deepEqual(commands.map(command=>command.id).sort((a,b)=>a-b),[16,19,20,21,22,115,178,201,203,206]);
  const expected={16:[4,0,0,0,557550000,375900000,80],19:[10,0,0,0,557550000,375900000,80],20:[0,0,0,0,0,0,0],21:[0,0,0,0,557550000,375900000,80],22:[0,0,0,0,557550000,375900000,80],115:[90,20,-1,1,0,0,0],178:[1,9,-1,0,0,0,0],201:[3,0,0,0,557550000,375900000,80],203:[0,0,0,0,1,0,0],206:[25,0,1,0,0,0,0]};
  const custom={16:{delay:4},115:{yaw:90,yawRate:20,direction:-1,relative:1},178:{speed:9},206:{distance:25,immediate:1}};
  for(const command of commands) {
    const item=missionItem({...point(),command:command.id,params:custom[command.id]??defaults(command.id)});
    assert.equal(item.command,command.id);
    assert.deepEqual([item.param1,item.param2,item.param3,item.param4,item.x,item.y,item.z],expected[command.id]);
  }
});
test('migrate legacy point commands into attached actions and mission settings without losing locations',()=>{
  const legacy=[{...point(),id:'start',command:22,alt:90},{...point(),id:'photo',command:203},{...point(),id:'hover',command:19,params:{duration:15}},{...point(),id:'land',command:21}].map(({actions,delay,...old})=>old);
  const mission=restoreMission(legacy);
  assert.equal(mission.waypoints.length,4);
  assert.equal(mission.waypoints[1].actions[0].command,203);
  assert.equal(mission.waypoints[2].actions[0].params.duration,15);
  assert.equal(mission.settings.takeoffAlt,90);
  assert.equal(mission.settings.ending,'land');
  assert.equal(mission.waypoints[1].lat,legacy[1].lat);
  assert.deepEqual(restoreMission(JSON.parse(JSON.stringify(mission))),mission);
});
test('reject invalid actions, coordinates, parameters, settings and repeated identifiers',()=>{
  assert.throws(()=>normalizePoint(null));
  for(const invalid of [{command:999},{delay:-1},{delay:1.5},{actions:[action(22)]},{actions:[action(178,{speed:0})]},{actions:[action(115,{yaw:0,yawRate:30,direction:0,relative:0})]},{actions:[action(201,{}, {target:{lat:91,lng:0,alt:80}})]},{actions:[action(203),action(203)]},{lat:91}])assert.throws(()=>point(invalid));
  assert.throws(()=>normalizeSettings({speed:Infinity}));
  assert.throws(()=>normalizeSettings({ending:'unknown'}));
  assert.throws(()=>restoreMission([point(),point()]));
});
test('each route point is exported before its ordered actions, with separate NAV anchors',()=>{
  const points=[point({delay:5,actions:[action(115,{yaw:90,yawRate:30,direction:1,relative:0}),action(203),action(19,{duration:10}),action(178,{speed:7})]}),point({id:'b',lat:56})];
  const mission=buildMission(points,{speed:12});
  assert.deepEqual(mission.items.map(item=>item.command),[22,16,178,16,16,115,203,19,16,178,19,16,20]);
  assert.equal(mission.items[2].param2,12);
  assert.equal(mission.items[4].param1,15);
  assert.equal(mission.items[9].param2,7);
  assert.equal(mission.items[10].param1,5);
  assert.equal(mission.items[11].x,560000000);
  assert.deepEqual(mission.items.map(item=>item.seq),mission.items.map((_,index)=>index));
  assert.doesNotMatch(JSON.stringify(mission),/[А-Яа-я]/);
});
test('camera and ROI never remove a route vertex; ROI target exports separately',()=>{
  const points=[point({actions:[action(203),action(201,{}, {target:{lat:57,lng:38,alt:30}})]}),point({id:'b',lat:56})];
  const settings=normalizeSettings({},points),path=flightPath(points,settings),mission=buildMission(points,settings);
  assert.deepEqual(path.map(value=>value.lat),[55.755,55.755,56,55.755]);
  assert.equal(mission.items.find(item=>item.command===201).x,570000000);
  assert.equal(mission.items.find(item=>item.command===201).z,30);
  assert.equal(path.some(value=>value.lat===57),false);
  assert.equal(mission.items.filter(item=>item.command===16&&item.x===560000000).length,1);
});
test('mission ending changes exported command and visible return segment; empty mission exports nothing',()=>{
  const points=[point()];
  const settings=normalizeSettings({home:{lat:55,lng:37},ending:'land',landing:{lat:54,lng:36,alt:50}},points);
  const mission=buildMission(points,settings);
  assert.equal(mission.items.at(-1).command,21);
  assert.equal(mission.items.at(-1).x,540000000);
  assert.equal(flightPath(points,settings).at(-1).lat,54);
  assert.equal(buildMission(points,{takeoff:false,ending:'hold'}).items.some(item=>[20,21,22].includes(item.command)),false);
  assert.ok(missionWarnings(points,{takeoff:false,ending:'hold'}).length===2);
  assert.deepEqual(buildMission([]).items,[]);
  assert.deepEqual(flightPath([],settings),[]);
});
test('simulation visits every point, runs attached actions in order, changes speed and returns Home',()=>{
  const points=[point({actions:[action(203),action(178,{speed:6})]}),point({id:'b',lat:55.756,delay:5})];
  const settings=normalizeSettings({home:{lat:55.754,lng:37.59}},points),steps=simulationSteps(points,settings);
  assert.deepEqual(steps.map(step=>step.label),['Взлёт','Перелёт к точке 1','Точка 1: Одиночный снимок','Точка 1: Изменить скорость','Перелёт к точке 2','Точка 2: остановка 5 с','Возврат домой','Посадка дома']);
  const firstLeg=steps[1],secondLeg=steps[4];
  assert.ok(Math.abs(secondLeg.seconds/firstLeg.seconds-2)<0.01);
  const mid=simulationFrame(steps,steps[0].seconds+firstLeg.seconds/2);
  assert.ok(mid.position.lat>settings.home.lat&&mid.position.lat<points[0].lat);
  const end=simulationFrame(steps,Infinity);
  assert.equal(end.done,true);assert.equal(end.position.lat,settings.home.lat);assert.equal(end.position.alt,0);
  assert.equal(simulationFrame([],0).position,null);
});
