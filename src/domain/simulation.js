import {meters} from './route.js';
import {commandInfo} from './mission.js';

export function simulationSteps(points,settings) {
  if (!points.length) return [];
  let current={...settings.home,alt:settings.takeoff?0:settings.takeoffAlt},speed=settings.speed;
  const steps=[];
  const add=(label,target,seconds)=>{steps.push({label,from:current,to:target,seconds:Math.max(0.1,seconds)});current=target;};
  if(settings.takeoff)add('Взлёт',{...current,alt:settings.takeoffAlt},settings.takeoffAlt/3);
  points.forEach((point,index)=>{
    const location={lat:point.lat,lng:point.lng,alt:point.alt};
    add(`Перелёт к точке ${index+1}`,location,Math.max(meters(current,location)/speed,Math.abs(current.alt-location.alt)/3));
    point.actions.forEach(action=>{
      const duration=action.command===19?action.params.duration:action.command===115?360/(action.params.yawRate||10):1;
      add(`Точка ${index+1}: ${commandInfo(action.command).label}`,location,duration);
      if(action.command===178)speed=action.params.speed;
    });
    if(point.delay)add(`Точка ${index+1}: остановка ${point.delay} с`,location,point.delay);
  });
  if(settings.ending==='rtl') {
    const target={...settings.home,alt:current.alt};
    add('Возврат домой',target,meters(current,target)/speed);
    add('Посадка дома',{...target,alt:0},target.alt/2);
  } else if(settings.ending==='land') {
    add('Подход к месту посадки',settings.landing,Math.max(meters(current,settings.landing)/speed,Math.abs(current.alt-settings.landing.alt)/3));
    add('Посадка',{...settings.landing,alt:0},settings.landing.alt/2);
  }
  return steps;
}
export function simulationFrame(steps,elapsed) {
  const total=steps.reduce((sum,step)=>sum+step.seconds,0);
  if(!steps.length)return {total:0,done:true,position:null,label:'Добавьте точки маршрута'};
  let remaining=Math.max(0,elapsed);
  for(const step of steps) {
    if(remaining<step.seconds) {
      const fraction=remaining/step.seconds;
      return {total,done:false,label:step.label,position:Object.fromEntries(['lat','lng','alt'].map(key=>[key,step.from[key]+(step.to[key]-step.from[key])*fraction]))};
    }
    remaining-=step.seconds;
  }
  return {total,done:true,position:steps.at(-1).to,label:'Предпросмотр завершён'};
}
