import {validPoint} from './route.js';

const field = (key,label,min,max,value,step='any') => ({key,label,min,max,value,step});
export const commands = [
  {id:22,label:'Взлёт',location:true,hint:'Для Copter: набор высоты над текущим местом. Обычно первая команда.',fields:[]},
  {id:16,label:'Путевая точка',location:true,hint:'Перелёт к точке и остановка на заданное время.',fields:[field('delay','Задержка, с',0,65535,0,1)]},
  {id:20,label:'Возврат домой',hint:'Возврат к home автопилота, а не к первой точке на карте.',fields:[]},
  {id:21,label:'Посадка',location:true,hint:'Посадка в выбранном месте. Завершающая команда.',fields:[]},
  {id:178,label:'Изменить скорость',hint:'Меняет горизонтальную скорость. Перелёт к маркеру не выполняется.',fields:[field('speed','Скорость, м/с',1,50,12)]},
  {id:19,label:'Зависание на время',location:true,hint:'Перелёт к точке и зависание на заданное время (Copter).',fields:[field('duration','Время, с',0,65535,10,1)]},
  {id:115,label:'Поворот носа',hint:'Задаёт курс. Перелёт к маркеру не выполняется.',fields:[field('yaw','Угол, °',0,360,0),field('yawRate','Скорость, °/с',0,360,30),field('direction','Направление: −1 / 1',-1,1,1,2),field('relative','Угол: 0 абс. / 1 отн.',0,1,0,1)]},
  {id:201,label:'Область интереса',location:true,hint:'Координаты маркера задают объект наблюдения, а не точку перелёта.',fields:[]},
  {id:206,label:'Съёмка через интервал',hint:'Интервал в метрах; 0 отключает съёмку. Перелёт к маркеру не выполняется.',fields:[field('distance','Интервал, м',0,10000,25),field('immediate','Снимок сразу: 0 / 1',0,1,0,1)]},
  {id:203,label:'Одиночный снимок',hint:'Один спуск затвора. Перелёт к маркеру не выполняется.',fields:[]},
];
export const commandInfo = id => commands.find(command=>command.id===id);
export const actionCommands=commands.filter(item=>[19,115,178,201,203,206].includes(item.id));
export function defaults(command,speed=12) {
  const info=commandInfo(command);
  if (!info) throw new Error('Неизвестная команда');
  return Object.fromEntries(info.fields.map(field=>[field.key,field.key==='speed'?speed:field.value]));
}
function parameters(command,raw={}) {
  const info=commandInfo(command),values={...defaults(command),...raw};
  for (const field of info.fields) {
    const value=values[field.key];
    if (!Number.isFinite(value)||value<field.min||value>field.max||(field.step!=='any'&&(value-field.min)%field.step!==0)) throw new Error(`Некорректное поле: ${field.label}`);
  }
  return Object.fromEntries(info.fields.map(field=>[field.key,values[field.key]]));
}
export function validLocation(value) {
  return value && Number.isFinite(value.lat)&&Math.abs(value.lat)<=90&&Number.isFinite(value.lng)&&Math.abs(value.lng)<=180;
}
export function normalizeAction(action,point) {
  if (!action||!actionCommands.some(item=>item.id===action.command)) throw new Error('Неизвестное действие точки');
  const result={id:action.id,command:action.command,params:parameters(action.command,action.params)};
  if (action.command===201) {
    const target=action.target??{lat:point.lat,lng:point.lng,alt:point.alt};
    if (!validLocation(target)||!Number.isFinite(target.alt)||target.alt<0||target.alt>500) throw new Error('Некорректные координаты ROI');
    result.target={lat:target.lat,lng:target.lng,alt:target.alt};
  }
  return result;
}
export function normalizePoint(point) {
  if (!point||!validPoint(point)||typeof point.id!=='string') throw new Error('Некорректная точка');
  const command=point.command??16;
  if (!commandInfo(command)) throw new Error('Неизвестная команда');
  if (point.actions!==undefined&&!Array.isArray(point.actions)) throw new Error('Некорректные действия');
  const legacy=point.actions===undefined&&actionCommands.some(item=>item.id===command);
  const actions=(point.actions??(legacy?[{id:`${point.id}-action`,command,params:point.params}]:[])).map((action,index)=>normalizeAction({...action,id:action.id??`${point.id}-action-${index}`},point));
  if (actions.length>30||new Set(actions.map(action=>action.id)).size!==actions.length) throw new Error('Слишком много действий или повторяющиеся идентификаторы');
  const delay=point.delay??(command===16?parameters(16,point.params).delay:0);
  parameters(16,{delay});
  return {id:point.id,lat:point.lat,lng:point.lng,alt:point.alt,delay,actions};
}
export function normalizeSettings(raw={},points=[]) {
  const first=points[0]??{lat:55.755,lng:37.59,alt:80},last=points.at(-1)??first;
  const settings={speed:12,takeoff:true,takeoffAlt:80,ending:'rtl',home:{lat:first.lat,lng:first.lng},landing:{lat:last.lat,lng:last.lng,alt:last.alt},...raw};
  if (!Number.isFinite(settings.speed)||settings.speed<1||settings.speed>50) throw new Error('Скорость должна быть от 1 до 50 м/с');
  if (typeof settings.takeoff!=='boolean'||!Number.isFinite(settings.takeoffAlt)||settings.takeoffAlt<5||settings.takeoffAlt>500) throw new Error('Некорректные параметры взлёта');
  if (!['rtl','land','hold'].includes(settings.ending)||!validLocation(settings.home)||!validLocation(settings.landing)||!validPoint(settings.landing)) throw new Error('Некорректное завершение или координаты Home');
  return settings;
}
export function restoreMission(data) {
  const raw=Array.isArray(data)?data:data?.waypoints;
  if (!Array.isArray(raw)||raw.length>100) throw new Error('Некорректная миссия');
  const points=raw.map(normalizePoint);
  if (new Set(points.map(point=>point.id)).size!==points.length) throw new Error('Повторяющиеся точки');
  const legacyTakeoff=raw.find(point=>point.command===22),legacyEnd=raw.findLast(point=>[20,21].includes(point.command));
  const inherited={};
  if (legacyTakeoff) Object.assign(inherited,{takeoff:true,takeoffAlt:legacyTakeoff.alt});
  if (legacyEnd) Object.assign(inherited,{ending:legacyEnd.command===20?'rtl':'land',...(legacyEnd.command===21?{landing:{lat:legacyEnd.lat,lng:legacyEnd.lng,alt:legacyEnd.alt}}:{})});
  return {version:3,waypoints:points,settings:normalizeSettings({...inherited,...data?.settings},points)};
}
export function flightPath(points,settings) {
  if (!points.length) return [];
  return [{...settings.home,alt:settings.takeoffAlt},...points,...(settings.ending==='rtl'?[{...settings.home,alt:points.at(-1).alt}]:settings.ending==='land'?[settings.landing]:[])];
}
export function missionItem({command,params={},...location}) {
  const p=parameters(command,params),info=commandInfo(command);
  const item={command,frame:3,param1:0,param2:0,param3:0,param4:0,x:0,y:0,z:0,autocontinue:1};
  if (info.location) {
    if (!validLocation(location)||!Number.isFinite(location.alt)) throw new Error('Некорректная позиция команды');
    Object.assign(item,{x:Math.round(location.lat*1e7),y:Math.round(location.lng*1e7),z:location.alt});
  }
  switch(command) {
    case 16:item.param1=p.delay;break;
    case 19:item.param1=p.duration;break;
    case 178:Object.assign(item,{param1:1,param2:p.speed,param3:-1});break;
    case 115:Object.assign(item,{param1:p.yaw,param2:p.yawRate,param3:p.direction,param4:p.relative});break;
    case 201:item.param1=3;break;
    case 206:Object.assign(item,{param1:p.distance,param3:p.immediate});break;
    case 203:item.x=1;break;
  }
  return item;
}
export function actionHoldSeconds(actions) {
  // Reserve time for DO/CONDITION processing before loading the next NAV command.
  return Math.min(65535,Math.max(3,actions.reduce((total,action)=>total+(action.command===115?Math.ceil(360/(action.params.yawRate||10))+2:1),0)));
}
export function buildMission(rawPoints,rawSettings={}) {
  const waypoints=rawPoints.map(normalizePoint),settings=normalizeSettings(rawSettings,waypoints),items=[];
  const push=(command,location,params={})=>items.push(missionItem({...location,command,params}));
  if (waypoints.length) {
    if (settings.takeoff) push(22,{...settings.home,alt:settings.takeoffAlt});
    push(16,{...settings.home,alt:settings.takeoffAlt},{delay:3});
    push(178,settings.home,{speed:settings.speed});
    waypoints.forEach(point=>{
      const actions=point.actions;
      push(16,point,{delay:actions.length?0:point.delay});
      let group=[];
      const flush=()=>{
        if (!group.length) return;
        push(16,point,{delay:actionHoldSeconds(group)});
        group.forEach(action=>push(action.command,action.target??point,action.params));
        group=[];
      };
      for (const action of actions) {
        if (action.command===19) {flush();push(19,point,action.params);}
        else group.push(action);
      }
      flush();
      if (actions.length&&point.delay) push(19,point,{duration:point.delay});
    });
    if (settings.ending==='rtl') push(20,settings.home);
    if (settings.ending==='land') push(21,settings.landing);
  }
  return {version:3,frame:'GLOBAL_RELATIVE_ALT',settings,waypoints,items:items.map((item,seq)=>({...item,seq,current:0}))};
}
export function missionWarnings(points,settings) {
  const warnings=[];
  if (!points.length) return warnings;
  if (!settings.takeoff) warnings.push('Взлёт отключён: миссия предполагает, что борт уже в воздухе.');
  if (settings.ending==='hold') warnings.push('Миссия завершится удержанием последней точки без посадки.');
  if (points.some(point=>point.actions.some(action=>action.command!==19))) warnings.push('В экспорт добавлены остановки для действий после прибытия. Их выполнение на борту требует проверки в SITL; DO/CONDITION могут быть пропущены при завершении NAV.');
  return warnings;
}
