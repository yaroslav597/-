import React, {useState} from 'react';
import {actionCommands,commandInfo,defaults,normalizePoint} from '../domain/mission.js';

export default function PointEditor({point,speed,onSave,onDelete,onPickRoi}) {
  const [draft,setDraft]=useState(point),[error,setError]=useState(''),[newCommand,setNewCommand]=useState(203);
  const change=(key,value)=>setDraft(previous=>({...previous,[key]:value}));
  const editAction=(id,changes)=>setDraft(previous=>({...previous,actions:previous.actions.map(action=>action.id===id?{...action,...changes}:action)}));
  function save(pickId) {
    try {const next=normalizePoint(draft);onSave(next);setError('');if(pickId)onPickRoi(next.id,pickId);} catch(error){setError(error.message);}
  }
  function move(index,offset) {
    const actions=[...draft.actions];
    [actions[index],actions[index+offset]]=[actions[index+offset],actions[index]];
    change('actions',actions);
  }
  return <form className="editor" onSubmit={event=>{event.preventDefault();save();}}>
    <h2>Настройки точки</h2><p className="muted">Точка всегда входит в маршрут. Действия выполняются после прибытия в указанном порядке.</p>
    {[['lat','Широта',-90,90],['lng','Долгота',-180,180],['alt','Высота от Home, м',5,500],['delay','Остановка после действий, с',0,65535]].map(([key,label,min,max])=><label key={key}>{label}<input required type="number" step={key==='delay'?1:'any'} min={min} max={max} value={draft[key]} onChange={event=>change(key,event.target.value===''?'':Number(event.target.value))}/></label>)}
    <h2>Действия в точке</h2>
    {!draft.actions.length&&<p className="muted">Действий пока нет.</p>}
    {draft.actions.map((action,index)=>{const info=commandInfo(action.command);return <fieldset className="action-card" key={action.id}>
      <legend>{index+1}. {info.label}</legend>
      {info.fields.map(field=><label key={field.key}>{field.label}<input required type="number" min={field.min} max={field.max} step={field.step} value={action.params[field.key]} onChange={event=>editAction(action.id,{params:{...action.params,[field.key]:event.target.value===''?'':Number(event.target.value)}})}/></label>)}
      {action.command===201&&<><p className="muted">Отдельный объект наблюдения. Линия маршрута к нему не идёт.</p>{[['lat','Широта ROI',-90,90],['lng','Долгота ROI',-180,180],['alt','Высота ROI, м',0,500]].map(([key,label,min,max])=><label key={key}>{label}<input required type="number" step="any" min={min} max={max} value={action.target[key]} onChange={event=>editAction(action.id,{target:{...action.target,[key]:event.target.value===''?'':Number(event.target.value)}})}/></label>)}<button type="button" onClick={()=>save(action.id)}>Выбрать ROI на карте</button></>}
      <div className="row"><button type="button" aria-label={`Поднять действие ${index+1}`} disabled={!index} onClick={()=>move(index,-1)}>↑</button><button type="button" aria-label={`Опустить действие ${index+1}`} disabled={index===draft.actions.length-1} onClick={()=>move(index,1)}>↓</button><button type="button" onClick={()=>change('actions',draft.actions.filter(item=>item.id!==action.id))}>Убрать действие</button></div>
    </fieldset>;})}
    <label>Новое действие<select value={newCommand} onChange={event=>setNewCommand(Number(event.target.value))}>{actionCommands.map(command=><option key={command.id} value={command.id}>{command.label}</option>)}</select></label>
    <button type="button" disabled={draft.actions.length>=30} onClick={()=>change('actions',[...draft.actions,{id:crypto.randomUUID(),command:newCommand,params:defaults(newCommand,speed),...(newCommand===201?{target:{lat:draft.lat,lng:draft.lng,alt:draft.alt}}:{})}])}>+ Добавить действие</button>
    {error&&<p role="alert">{error}</p>}
    <div className="row"><button type="submit">Сохранить точку</button><button type="button" onClick={onDelete}>Удалить точку</button></div>
  </form>;
}
