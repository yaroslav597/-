import test from 'node:test';
import assert from 'node:assert/strict';
import {describeDifference,explainBridgeError} from '../src/domain/missionLabels.js';

test('coordinate mismatches are degrees with enough precision to see the difference',()=>{
  const result=describeDifference({seq:2,field:'x',expected:555708379,actual:557550000},[{seq:2,command:16}]);
  assert.match(result.title,/широта/);
  assert.equal(result.planned,'55,5708379°');
  assert.equal(result.onboard,'55,7550000°');
});
test('count has its own heading without an undefined command number',()=>{
  const result=describeDifference({seq:null,field:'count',expected:12,actual:9});
  assert.equal(result.title,'Количество команд, включая точку старта');
  assert.equal(result.planned,'12');assert.equal(result.onboard,'9');
});
test('expected command determines units when the on-board command differs',()=>{
  const result=describeDifference({seq:1,field:'param2',expected:13,actual:12},[{seq:1,command:16}],[{command:178}]);
  assert.match(result.title,/скорость/);assert.equal(result.planned,'13 м/с');
});
test('photo shutter is not shown as latitude; unavailable parameters remain readable',()=>{
  const result=describeDifference({seq:1,field:'x',expected:1,actual:0},[{seq:1,command:203}]);
  assert.match(result.title,/спуск затвора/);assert.equal(result.planned,'Сделать снимок');assert.equal(result.onboard,'Не делать снимок');
  assert.equal(describeDifference({seq:1,field:'param2',expected:12,actual:null},[{seq:1,command:178}]).onboard,'не задано');
});
test('command and frame numbers become names',()=>{
  assert.equal(describeDifference({seq:1,field:'command',expected:20,actual:21}).planned,'Возврат домой');
  assert.equal(describeDifference({seq:1,field:'frame',expected:3,actual:0},[{seq:1,command:16}]).onboard,'От уровня моря');
});
test('home error includes an actionable explanation and other errors are preserved',()=>{
  const result=explainBridgeError('Плановый Home отличается от Home автопилота более чем на 20 м');
  assert.match(result,/дальше 20 м/);assert.doesNotMatch(result,/Home/);
  assert.equal(explainBridgeError('Нет подтверждения MAVLink'),'Нет подтверждения MAVLink');
});
