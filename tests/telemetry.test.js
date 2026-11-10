import test from 'node:test';
import assert from 'node:assert/strict';
import {validTelemetry,subscribeWebSocket} from '../src/services/telemetry.js';

test('telemetry validates numeric fields and allows unknown values',()=>{
  assert.equal(validTelemetry({timestamp:Date.now(),altitude:80,battery:null,heading:null}),true);
  assert.equal(validTelemetry({timestamp:Date.now(),speed:'12'}),false);
  assert.equal(validTelemetry({timestamp:Date.now(),lat:NaN}),false);
  assert.equal(validTelemetry(null),false);
  assert.equal(validTelemetry({altitude:80}),false);
});

test('WebSocket routes events, clears stale telemetry and cleans up handlers',()=>{
  const previous=globalThis.WebSocket,sockets=[],received=[],statuses=[],events=[];
  class FakeSocket {
    constructor(){sockets.push(this);}
    close(){this.closed=true;}
  }
  globalThis.WebSocket=FakeSocket;
  let stop;
  try {
    stop=subscribeWebSocket('ws://test',value=>received.push(value),value=>statuses.push(value),value=>events.push(value));
    const socket=sockets[0];socket.onopen();
    socket.onmessage({data:JSON.stringify({type:'telemetry',payload:{timestamp:Date.now(),altitude:80}})});
    assert.equal(received.at(-1).altitude,80);
    socket.onmessage({data:JSON.stringify({type:'telemetry',payload:{timestamp:Date.now()-6000,altitude:90}})});
    assert.equal(received.at(-1),null);
    socket.onmessage({data:JSON.stringify({type:'status',payload:{connected:true}})});
    assert.equal(events[0].payload.connected,true);
    socket.onmessage({data:'{'});
    assert.equal(statuses.at(-1),'invalid-message');
    socket.onclose();
    assert.equal(statuses.at(-1),'disconnected');
    stop();assert.equal(socket.closed,true);assert.equal(socket.onmessage,null);
  } finally {stop?.();globalThis.WebSocket=previous;}
});
