import React, {useEffect,useMemo,useState} from 'react';
import {simulationSteps,simulationFrame} from '../domain/simulation.js';

export default function Simulation({points,settings,onFrame}) {
  const steps=useMemo(()=>simulationSteps(points,settings),[points,settings]);
  const [elapsed,setElapsed]=useState(0),[running,setRunning]=useState(false),[rate,setRate]=useState(10),[started,setStarted]=useState(false);
  const frame=simulationFrame(steps,elapsed);
  useEffect(()=>{
    if(!running)return;
    let last=performance.now();
    const timer=setInterval(()=>{const now=performance.now();setElapsed(previous=>Math.min(frame.total,previous+(now-last)/1000*rate));last=now;},100);
    return ()=>clearInterval(timer);
  },[running,rate,frame.total]);
  useEffect(()=>{if(frame.done)setRunning(false);},[frame.done]);
  useEffect(()=>{onFrame(started?frame.position:null);},[elapsed,started,onFrame,steps]);
  useEffect(()=>()=>onFrame(null),[onFrame]);
  return <div className="simulation-panel"><h2>Предпросмотр прохождения</h2><p className="muted">Упрощённая демонстрация маршрута и действий. Это не симулятор автопилота; время и поведение борта могут отличаться.</p>
    <div className="row simulation-controls"><button disabled={!points.length} onClick={()=>{if(frame.done)setElapsed(0);setStarted(true);setRunning(previous=>!previous);}}>{running?'Пауза':started&&!frame.done?'Продолжить':'Запустить предпросмотр'}</button><button disabled={!started} onClick={()=>{setRunning(false);setElapsed(0);setStarted(false);}}>Сбросить</button><label>Темп<select value={rate} onChange={event=>setRate(Number(event.target.value))}><option value="1">×1</option><option value="10">×10</option><option value="50">×50</option></select></label></div>
    <progress value={elapsed} max={frame.total||1}/><p role="status">{started?frame.label:'Готов к запуску'} · {Math.floor(elapsed)} / {Math.ceil(frame.total)} с</p>
  </div>;
}
