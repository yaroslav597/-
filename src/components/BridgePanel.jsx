import React, {useEffect,useRef,useState} from 'react';
import {api,telemetryUrl} from '../services/api';
import {subscribeWebSocket} from '../services/telemetry';
import {describeDifference,explainBridgeError} from '../domain/missionLabels';

const labels={queued:'В очереди',running:'Передача в автопилот',succeeded:'Подтверждено автопилотом',failed:'Ошибка'};
export default function BridgePanel({plan,source,onSource,onTelemetry,onLink,onVerified}) {
  const [connection,setConnection]=useState('disconnected'),[status,setStatus]=useState(null),[operation,setOperation]=useState(null),[submittedFingerprint,setSubmittedFingerprint]=useState(null),[saved,setSaved]=useState(null),[pending,setPending]=useState(false),[error,setError]=useState('');
  const currentOperation=useRef(null),mounted=useRef(true);
  const [submittedItems,setSubmittedItems]=useState([]);
  useEffect(()=>{mounted.current=true;return ()=>{mounted.current=false;};},[]);
  useEffect(()=>{
    if(source!=='backend'){setStatus(null);onLink(null);return;}
    return subscribeWebSocket(telemetryUrl,onTelemetry,value=>{setConnection(value);if(value!=='connected'){setStatus(null);onLink(null);}},event=>{
      if(event.type==='status'){setStatus(event.payload);onLink(event.payload);}
      if(event.type==='operation'&&event.payload.operationId===currentOperation.current)setOperation(event.payload);
    });
  },[source,onTelemetry,onLink]);
  const operationId=operation?.operationId,terminal=operation&&['succeeded','failed'].includes(operation.status);
  useEffect(()=>{
    if(!operationId||terminal)return;
    let cancelled=false;
    const poll=async()=>{try{const next=await api.operation(operationId);if(!cancelled)setOperation(next);}catch{/* Keep the operation id; retry GET, never repeat the upload automatically. */}};
    poll();const timer=setInterval(poll,1500);
    return ()=>{cancelled=true;clearInterval(timer);};
  },[operationId,terminal]);
  const fingerprint=JSON.stringify(plan),busy=pending||Boolean(operation&&!terminal)||status?.busy;
  async function send(action) {
    setPending(true);setError('');
    try {
      let record=saved;
      if(!record||record.fingerprint!==fingerprint){const response=await api.save(plan);record={missionId:response.missionId,fingerprint,items:response.items};if(mounted.current)setSaved(record);}
      if(action){const job=await (action==='verify'?api.verify(record.missionId):api.upload(record.missionId));currentOperation.current=job.operationId;if(mounted.current){setOperation(job);setSubmittedFingerprint(fingerprint);setSubmittedItems(record.items??[]);}}
    }catch(error){if(mounted.current)setError(error.message);}
    finally{if(mounted.current)setPending(false);}
  }
  async function flight(action) {
    setPending(true);setError('');
    try {
      const job=await api.flight(action,action==='start'?saved?.missionId:undefined);
      currentOperation.current=job.operationId;
      if(mounted.current){setOperation(job);setSubmittedFingerprint(fingerprint);}
    }catch(error){if(mounted.current)setError(error.message);}
    finally{if(mounted.current)setPending(false);}
  }
  const verified=Boolean(saved&&saved.fingerprint===fingerprint&&status?.verifiedMissionId===saved.missionId);
  useEffect(()=>{onVerified(verified);},[verified,onVerified]);
  const connected=source==='backend'&&connection==='connected';
  return <div className="bridge-panel"><h2>Связь с backend</h2>
    <label>Источник телеметрии<select value={source} onChange={event=>onSource(event.target.value)}><option value="demo">Демонстрация</option><option value="backend">Backend / MAVLink</option></select></label>
    {source==='backend'&&<>
      <p className="muted">Сервер: {connected?'подключён':connection==='connecting'?'подключение…':'нет связи'} · Автопилот: {status?.connected?'подключён':'ожидается сигнал связи'}</p>
      {status?.connected&&<p className="muted">Режим: {status.mode??'—'} · {status.armed?'ARM включён':'ARM выключен'}</p>}
      {status?.connected&&status.firmware&&<p className="muted">ArduPilot {status.firmware}</p>}
      {status?.home&&<p className="muted">Точка старта борта: {status.home.lat.toFixed(5)}°, {status.home.lng.toFixed(5)}°</p>}
      <div className="row"><button disabled={!plan.waypoints.length||busy} onClick={()=>send(false)}>Сохранить на сервере</button><button disabled={!plan.waypoints.length||busy||!status?.connected||!status?.home||status?.armed||!connected} onClick={()=>send('upload')}>Загрузить в автопилот</button><button disabled={!plan.waypoints.length||busy||!status?.connected||!connected} onClick={()=>send('verify')}>Проверить миссию на борту</button></div>
      {saved&&<p className="muted">{saved.fingerprint===fingerprint?'Текущая миссия сохранена на сервере.':'Миссия изменена. Перед загрузкой будет сохранена новая версия.'}</p>}
      <div className="flight-controls"><h2>Управление полётом</h2>{status?.missionState===5&&status?.startConsumed&&!status?.armed&&status?.landedState===1&&<p className="mission-match">Миссия завершена · аппарат на земле</p>}
        <p className="muted">{!status?.connected?'Ожидание связи':status.landedState===1?(status.armed?'На земле · готов к запуску':'На земле · двигатели выключены'):status.landedState===2?'В воздухе':status.landedState===3?'Взлёт':status.landedState===4?'Посадка':'Состояние посадки уточняется'}</p>
        <div className="row"><button disabled={!connected||!status?.connected||busy||status?.armed||status?.landedState!==1} onClick={()=>flight('arm')}>Подготовить к полёту (ARM)</button><button disabled={!connected||!status?.connected||busy||!status?.armed||status?.landedState!==1||status?.startConsumed||(status?.missionState===5&&!status?.uploadedMissionId)||!verified||!plan.settings.takeoff} onClick={()=>flight('start')}>Запустить миссию</button></div>
        {!verified&&<p className="muted">Перед запуском нажмите «Проверить миссию на борту». После изменения плана загрузите и проверьте его заново.</p>}
        <div className="row"><button disabled={!connected||!status?.connected||busy||!status?.armed} onClick={()=>flight('rtl')}>Возврат домой</button><button disabled={!connected||!status?.connected||busy||!status?.armed} onClick={()=>flight('land')}>Посадка здесь</button><button disabled={!connected||!status?.connected||busy||!status?.armed||status?.landedState!==1} onClick={()=>flight('disarm')}>Выключить ARM</button></div>
        {status?.currentSeq!=null&&<p className="muted">{status.currentSeq===0?'Home · служебная точка':`Текущая команда: ${status.currentSeq} из ${status.missionCount||'—'}`} · отмечено пройденных команд: {status.reached?.filter(seq=>seq>0).length??0}</p>}
        {status?.lastText&&<p className="autopilot-message">Автопилот: {status.lastText}</p>}
      </div>
      {operation&&<p role="status">{operation.kind==='flight'?(operation.status==='succeeded'?'Действие подтверждено':operation.status==='failed'?'Ошибка управления':'Выполнение команды'):operation.kind==='verify'&&operation.status==='running'?'Чтение миссии с борта':operation.kind==='verify'&&operation.status==='succeeded'?'Миссия прочитана':labels[operation.status]??operation.status} · {operation.progress}/{operation.total}{operation.error?` · ${operation.error}`:''}<small>Операция: {operation.operationId}</small></p>}
      {operation?.result?.matches!==undefined&&<div className={operation.result.matches?'mission-match':'mission-warning'}><p>{operation.result.matches?'Миссия на борту совпадает с проверяемым планом.':'Миссия на борту отличается от проверяемого плана.'}</p>{operation.result.differences.slice(0,10).map((difference,index)=>{const description=describeDifference(difference,operation.result.items,submittedItems);return <div className="mission-difference" key={index}><b>{description.title}</b><p>В плане: {description.planned}</p><p>На борту: {description.onboard}</p></div>;})}{operation.result.differences.length>10&&<p>Показаны первые 10 из {operation.result.differences.length} различий.</p>}</div>}
      {operation&&submittedFingerprint!==fingerprint&&<p className="muted">Операция относится к ранее отправленной версии. Текущая миссия изменена.</p>}
      {error&&<p className="mission-warning" role="alert">{explainBridgeError(error)}</p>}
      {status?.error&&<p className="muted">{explainBridgeError(status.error)}</p>}
      <p className="muted">Сохранение на сервере и загрузка на борт — отдельные операции. Успех загрузки появится после подтверждения автопилота. Загрузка не запускает полёт.</p>
    </>}
  </div>;
}
