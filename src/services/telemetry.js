export function subscribeDemo(listener) {
  let elapsed = 0;
  const publish = () => { elapsed++; listener({altitude:80+Math.sin(elapsed/8)*2, speed:12+Math.sin(elapsed/5), battery:Math.max(20,98-elapsed/120), satellites:18, heading:(elapsed*2)%360, mode:'DEMO', timestamp:Date.now()}); };
  publish(); const timer = setInterval(publish,1000);
  return () => clearInterval(timer);
}
export function validTelemetry(payload) {
  if(!payload||typeof payload!=='object'||!Number.isFinite(payload.timestamp))return false;
  return ['altitude','speed','battery','satellites','heading','lat','lng'].every(key=>payload[key]==null||Number.isFinite(payload[key]));
}
export function subscribeWebSocket(url,listener,onStatus,onEvent=()=>{}) {
  let socket,reconnect,stopped=false,attempt=0,lastMessage=0;
  const connect=()=>{
    if(stopped)return;
    onStatus('connecting');
    socket=new WebSocket(url);
    socket.onopen=()=>{attempt=0;lastMessage=Date.now();onStatus('connected');};
    socket.onmessage=event=>{
      if(stopped)return;
      try {
        const data=JSON.parse(event.data);
        if(data.type==='telemetry') {
          if(!validTelemetry(data.payload))throw new Error('Invalid telemetry');
          lastMessage=Date.now();
          onStatus('connected');
          const stale=data.payload.stale||Date.now()-data.payload.timestamp>5000;
          listener(stale?null:data.payload);
        } else if(['status','operation','mission_current'].includes(data.type)&&data.payload&&typeof data.payload==='object')onEvent(data);
      } catch {onStatus('invalid-message');}
    };
    socket.onerror=()=>onStatus('error');
    socket.onclose=()=>{
      if(stopped)return;
      listener(null);onStatus('disconnected');
      reconnect=setTimeout(connect,Math.min(8000,1000*2**attempt++));
    };
  };
  const watchdog=setInterval(()=>{if(lastMessage&&Date.now()-lastMessage>5000){listener(null);onStatus('stale');if(socket?.readyState===1)socket.close();}},1000);
  connect();
  return ()=>{stopped=true;clearTimeout(reconnect);clearInterval(watchdog);if(socket){socket.onclose=null;socket.onerror=null;socket.onmessage=null;socket.onopen=null;socket.close();}};
}
