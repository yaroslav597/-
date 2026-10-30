export function subscribeDemo(listener) {
  let elapsed = 0;
  const publish = () => { elapsed++; listener({altitude:80+Math.sin(elapsed/8)*2, speed:12+Math.sin(elapsed/5), battery:Math.max(20,98-elapsed/120), satellites:18, heading:(elapsed*2)%360, mode:'DEMO', timestamp:Date.now()}); };
  publish(); const timer = setInterval(publish,1000);
  return () => clearInterval(timer);
}
export function subscribeWebSocket(url, listener, onStatus) {
  const socket = new WebSocket(url);
  socket.onopen = () => onStatus('connected');
  socket.onmessage = event => { try { const data = JSON.parse(event.data); if (data.type==='telemetry') listener(data.payload); } catch { onStatus('invalid-message'); } };
  socket.onerror = () => onStatus('error');
  socket.onclose = () => onStatus('disconnected');
  return () => socket.close();
}
