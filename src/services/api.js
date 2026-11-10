const base=(import.meta.env?.VITE_API_URL??'http://127.0.0.1:8000').replace(/\/$/,'');
export const telemetryUrl=`${base.replace(/^http/,'ws')}/ws/telemetry`;

async function request(path,options={}) {
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  try {
    const response=await fetch(`${base}${path}`,{...options,signal:controller.signal,headers:{'Content-Type':'application/json',...options.headers}});
    const data=await response.json();
    if(!response.ok) {
      const detail=Array.isArray(data.detail)?data.detail.map(item=>`${item.loc.join('.')}: ${item.msg}`).join('; '):data.detail;
      throw new Error(detail??`Ошибка сервера: ${response.status}`);
    }
    return data;
  } catch(error) {
    if(error.name==='AbortError')throw new Error('Сервер не ответил вовремя. Результат отправленного запроса нужно проверить перед повтором.');
    if(error instanceof TypeError)throw new Error('Backend недоступен. Запустите сервер на порту 8000.');
    throw error;
  } finally {clearTimeout(timer);}
}
export const api={
  flight:(action,missionId)=>request('/api/flight',{method:'POST',body:JSON.stringify({action,...(missionId?{missionId}:{})})}),
  save:plan=>request('/api/missions',{method:'POST',body:JSON.stringify(plan)}),
  upload:missionId=>request('/api/uploads',{method:'POST',body:JSON.stringify({missionId})}),
  verify:missionId=>request('/api/mission-checks',{method:'POST',body:JSON.stringify({missionId})}),
  operation:id=>request(`/api/operations/${id}`),
  status:()=>request('/api/status'),
};
