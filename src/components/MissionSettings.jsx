import React from 'react';

export default function MissionSettings({settings,onChange,onPick}) {
  const number=(key,label,min,max)=><label>{label}<input type="number" step="any" min={min} max={max} value={settings[key]} onChange={event=>{const value=event.target.valueAsNumber;if(Number.isFinite(value))onChange({...settings,[key]:Math.min(max,Math.max(min,value))});}}/></label>;
  return <div className="options mission-settings">
    <h2>Начало и завершение</h2>
    <label><input type="checkbox" checked={settings.takeoff} onChange={event=>onChange({...settings,takeoff:event.target.checked})}/> Взлёт перед маршрутом</label>
    {settings.takeoff&&number('takeoffAlt','Высота взлёта, м',5,500)}
    {number('speed','Скорость, м/с',1,50)}
    <div className="location-card"><b>Home — место старта</b><small>{settings.home.lat.toFixed(5)}, {settings.home.lng.toFixed(5)}</small><button onClick={()=>onPick('home')}>Указать Home на карте</button><p className="muted">Плановый Home. Перед полётом его нужно сверить с Home автопилота.</p></div>
    <label>Завершение<select value={settings.ending} onChange={event=>onChange({...settings,ending:event.target.value})}><option value="rtl">Возврат домой</option><option value="land">Посадка в выбранном месте</option><option value="hold">Остаться в последней точке</option></select></label>
    {settings.ending==='land'&&<div className="location-card"><b>Место посадки</b><small>{settings.landing.lat.toFixed(5)}, {settings.landing.lng.toFixed(5)}</small><button onClick={()=>onPick('landing')}>Указать посадку на карте</button><label>Высота подхода, м<input type="number" min="5" max="500" value={settings.landing.alt} onChange={event=>{const value=event.target.valueAsNumber;if(Number.isFinite(value))onChange({...settings,landing:{...settings.landing,alt:Math.min(500,Math.max(5,value))}});}}/></label></div>}
  </div>;
}
