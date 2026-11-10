import React, {useEffect,useMemo,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import 'leaflet/dist/leaflet.css';
import './style.css';
import Map from './components/Map';
import PointEditor from './components/PointEditor';
import MissionSettings from './components/MissionSettings';
import Simulation from './components/Simulation';
import BridgePanel from './components/BridgePanel';
import {normalizePoint,restoreMission,commandInfo,flightPath,buildMission,missionWarnings} from './domain/mission';
import {simulationSteps,simulationFrame} from './domain/simulation';
import {length} from './domain/route';
import {subscribeDemo} from './services/telemetry';

const initial=[[55.755,37.59],[55.745,37.63],[55.76,37.625],[55.743,37.60]].map(([lat,lng],index)=>({id:`demo-${index}`,lat,lng,alt:80}));
function restore() {
  try {const data=JSON.parse(localStorage.getItem('mission'));return restoreMission(data??initial);}
  catch {return restoreMission(initial);}
}
function App() {
  const [source,setSource]=useState('demo'),[link,setLink]=useState(null);
  const [track,setTrack]=useState([]),[verified,setVerified]=useState(false),wasArmed=useRef(false);
  const [plan,setPlan]=useState(restore),[selected,setSelected]=useState(null),[telemetry,setTelemetry]=useState(null),[vehicle,setVehicle]=useState(null),[mode,setMode]=useState(null),[message,setMessage]=useState('Нажмите на карту, чтобы добавить точку');
  const {waypoints:points,settings}=plan;
  useEffect(()=>{setTelemetry(null);if(source==='demo')return subscribeDemo(setTelemetry);},[source]);
  useEffect(()=>{setTrack([]);wasArmed.current=false;},[source]);
  useEffect(()=>{
    if(source!=='backend')return;
    if(link?.armed&&!wasArmed.current)setTrack([]);
    wasArmed.current=Boolean(link?.armed);
  },[source,link?.armed]);
  useEffect(()=>{
    if(source!=='backend'||!link?.armed||!Number.isFinite(telemetry?.lat)||!Number.isFinite(telemetry?.lng))return;
    setTrack(previous=>{
      const last=previous.at(-1);
      if(last&&Math.abs(last.lat-telemetry.lat)+Math.abs(last.lng-telemetry.lng)<0.000001)return previous;
      return [...previous.slice(-1999),{lat:telemetry.lat,lng:telemetry.lng}];
    });
  },[source,telemetry,link?.armed]);
  useEffect(()=>{try{localStorage.setItem('mission',JSON.stringify(plan));}catch{setMessage('Не удалось сохранить миссию в браузере');}},[plan]);
  const active=points.find(point=>point.id===selected),mission=useMemo(()=>buildMission(points,settings),[points,settings]),warnings=missionWarnings(points,settings);
  const reachedKey=JSON.stringify(link?.reached??[]);
  const reachedItems=useMemo(()=>source==='backend'&&verified?JSON.parse(reachedKey).map(seq=>mission.items[seq-1]).filter(Boolean):[],[source,verified,reachedKey,mission]);
  const total=length(flightPath(points,settings)),estimated=simulationFrame(simulationSteps(points,settings),0).total;
  function setPoints(updater) {setPlan(previous=>({...previous,waypoints:typeof updater==='function'?updater(previous.waypoints):updater}));}
  function updatePoint(id,changes) {setPoints(previous=>previous.map(point=>point.id===id?normalizePoint({...point,...changes}):point));}
  function setSettings(next) {setPlan(previous=>({...previous,settings:next}));}
  function moveLocation(kind,position) {setPlan(previous=>({...previous,settings:{...previous.settings,[kind]:{...previous.settings[kind],lat:position.lat,lng:position.lng}}}));}
  function moveRoi(pointId,actionId,position) {setPoints(previous=>previous.map(point=>point.id===pointId?{...point,actions:point.actions.map(action=>action.id===actionId?{...action,target:{...action.target,lat:position.lat,lng:position.lng}}:action)}:point));}
  function mapClick(position) {
    if(mode) {
      if(mode.kind==='roi')moveRoi(mode.pointId,mode.actionId,position);else moveLocation(mode.kind,position);
      setMode(null);setMessage('Положение сохранено');return;
    }
    if(points.length>=100){setMessage('Достигнут предел: 100 точек');return;}
    const next=normalizePoint({id:crypto.randomUUID(),lat:position.lat,lng:position.lng,alt:80});
    setPoints(previous=>[...previous,next]);setSelected(next.id);setMessage('Точка добавлена. Настройте действия и сохраните её.');
  }
  function exportMission() {
    const url=URL.createObjectURL(new Blob([JSON.stringify(mission,null,2)],{type:'application/json'}));
    const anchor=document.createElement('a');anchor.href=url;anchor.download='mission.json';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  return <><header><div className="brand">✥ <b>АЭРО</b><span>НАЗЕМНАЯ СТАНЦИЯ</span></div><div className="status">● {source==='demo'?'Демонстрационный режим':link?.connected?'MAVLink подключён':'Нет связи с автопилотом'}</div><span className="version">GCS / 01</span></header>
    <main><aside><div className="eyebrow">ПЛАНИРОВАНИЕ МИССИИ</div><h1>Полётное задание</h1><p className="muted">Постройте маршрут и добавьте действия в нужных точках.</p>
      <div className="summary"><div><small>РАССТОЯНИЕ</small><strong>{(total/1000).toFixed(2)} <em>км</em></strong></div><div><small>ВРЕМЯ · ОЦЕНКА</small><strong>{(estimated/60).toFixed(1)} <em>мин</em></strong></div></div>
      <BridgePanel plan={plan} source={source} onSource={setSource} onTelemetry={setTelemetry} onLink={setLink} onVerified={setVerified}/><MissionSettings settings={settings} onChange={setSettings} onPick={kind=>setMode({kind})}/>
      <div className="list-title"><h2>Путевые точки <span>{points.length}</span></h2><button onClick={()=>{setPoints([]);setSelected(null);setMode(null);}}>Очистить</button></div>
      <div className="point-list">{points.map((point,index)=><button className={`point ${selected===point.id?'selected':''}`} key={point.id} onClick={()=>{setSelected(point.id);setMode(null);}}><span className="number">{index+1}</span><span><b>Точка {index+1}</b><small>{point.lat.toFixed(5)}, {point.lng.toFixed(5)}</small><small>{point.actions.length?point.actions.map(action=>commandInfo(action.command).label).join(' → '):'Без дополнительных действий'}</small></span><span>{point.alt} м</span></button>)}{!points.length&&<p className="muted">Добавьте первую точку на карте.</p>}</div>
      {active&&<PointEditor key={JSON.stringify(active)} point={active} speed={settings.speed} onSave={next=>{updatePoint(active.id,next);setMessage('Точка и действия сохранены');}} onDelete={()=>{setPoints(previous=>previous.filter(point=>point.id!==active.id));setSelected(null);setMode(null);}} onPickRoi={(pointId,actionId)=>setMode({kind:'roi',pointId,actionId})}/>}
      <button disabled={!points.length} onClick={exportMission}>↓ Экспорт задания JSON</button>
    </aside><section className="workspace">
      <div className="map-title"><div><span className="eyebrow">РАБОЧАЯ ОБЛАСТЬ</span><h2>Карта маршрута</h2></div><span className="badge">WGS 84</span></div>
      <div className="map-tools"><span>H — Home</span><span>◎ — объект ROI</span><span>L — посадка</span><span>Пунктир — план · зелёная линия — фактический полёт · тонкий пунктир — взгляд на ROI</span></div>
      {mode&&<div className="pick-banner" role="status">{mode.kind==='home'?'Укажите Home':mode.kind==='landing'?'Укажите место посадки':'Укажите объект ROI'} нажатием на карту.<button onClick={()=>setMode(null)}>Отмена</button></div>}
      <div className="map-wrap"><Map points={points} settings={settings} track={source==='backend'?track:[]} currentItem={source==='backend'&&verified?mission.items[(link?.currentSeq??0)-1]:null} reachedItems={reachedItems} vehicle={source==='backend'?(Number.isFinite(telemetry?.lat)&&Number.isFinite(telemetry?.lng)?telemetry:null):vehicle} onSelect={setSelected} onMove={(id,position)=>updatePoint(id,{lat:position.lat,lng:position.lng})} onMoveLocation={moveLocation} onMoveRoi={moveRoi} onAdd={mapClick}/><div className="hint" role="status">{mode?'Выберите место на карте. Новая путевая точка не будет добавлена.':message}</div></div>
      {source==='demo'&&<Simulation key={JSON.stringify(plan)} points={points} settings={settings} onFrame={setVehicle}/>}
      <div className="mission-preview"><h2>Предпросмотр миссии</h2><p className="muted">Порядок: взлёт → точки и действия → завершение. Остановки для выполнения действий добавляются автоматически.</p>{warnings.map(warning=><p className="mission-warning" key={warning}>{warning}</p>)}
        <details><summary>Команды MAVLink · {mission.items.length}</summary><div className="table-wrap"><table><thead><tr><th>№</th><th>Команда</th><th>Код</th><th>Параметры 1–4</th><th>Координаты / значение 5–7</th></tr></thead><tbody>{mission.items.map(item=><tr key={item.seq} className={source==='backend'&&verified?(link?.currentSeq===item.seq+1?'current-command':link?.reached?.includes(item.seq+1)?'reached-command':''):''}><td>{item.seq+1}</td><td>{commandInfo(item.command).label}</td><td>{item.command}</td><td>{[item.param1,item.param2,item.param3,item.param4].join(' / ')}</td><td>{commandInfo(item.command).location?`${(item.x/1e7).toFixed(5)}, ${(item.y/1e7).toFixed(5)}, ${item.z} м`:[item.x,item.y,item.z].join(' / ')}</td></tr>)}</tbody></table></div></details>
      </div>
      <div className="telemetry-head"><h2>{source==='demo'?'Демо-телеметрия':'Телеметрия автопилота'}</h2><span>{source==='demo'?'● Синтетические данные · 1 Гц':telemetry?'● Данные MAVLink':'Ожидание свежих данных'}</span></div><div className="telemetry">{[['Высота',telemetry?.altitude?.toFixed(1),'м'],['Скорость',telemetry?.speed?.toFixed(1),'м/с'],['Батарея',telemetry?.battery?.toFixed(0),'%'],['Спутники',telemetry?.satellites,'GPS'],['Курс',telemetry?.heading,'°']].map(([label,value,unit])=><article key={label}><small>{label}</small><strong>{value??'—'} <em>{unit}</em></strong><div className="meter"/></article>)}</div><footer>{source==='demo'?'Демо-телеметрия независима от предпросмотра.':'Режим MAVLink. Загрузка миссии не включает ARM и не запускает полёт.'}</footer>
    </section></main></>;
}
createRoot(document.getElementById('root')).render(<App/>);
