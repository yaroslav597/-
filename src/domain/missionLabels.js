import {commandInfo} from './mission.js';

const locationCommands=new Set([16,19,21,22,201]);
const number=new Intl.NumberFormat('ru-RU',{maximumFractionDigits:3,useGrouping:false});
const coordinates=new Intl.NumberFormat('ru-RU',{minimumFractionDigits:7,maximumFractionDigits:7,useGrouping:false});
const numeric=value=>Number.isFinite(value)?number.format(value):value==null?'не задано':String(value);
const units=unit=>value=>Number.isFinite(value)?`${numeric(value)} ${unit}`:numeric(value);
const choices=values=>value=>values[value]??numeric(value);
const commandName=value=>commandInfo(value)?.label??`Неизвестная команда (${numeric(value)})`;

function fieldInfo(field,command) {
  if(field==='command')return ['Назначение',commandName];
  if(field==='frame')return ['Отсчёт высоты',choices({0:'От уровня моря',5:'От уровня моря',3:'От точки старта',6:'От точки старта',10:'Над рельефом',11:'Над рельефом',2:'Без координат'})];
  if(locationCommands.has(command)) {
    if(field==='x'||field==='y')return [field==='x'?'Широта':'Долгота',value=>Number.isFinite(value)?`${coordinates.format(value/1e7)}°`:numeric(value)];
    if(field==='z')return ['Высота',units('м')];
  }
  const fields={
    16:{param1:['Остановка в точке',units('с')]},
    19:{param1:['Время зависания',units('с')]},
    178:{param2:['Скорость',units('м/с')]},
    115:{param1:['Угол поворота',units('°')],param2:['Скорость поворота',units('°/с')],param3:['Направление поворота',choices({'-1':'Против часовой стрелки',1:'По часовой стрелке',0:'Кратчайший путь'})],param4:['Способ задания угла',choices({0:'Абсолютный курс',1:'Относительный поворот'})]},
    201:{param1:['Режим наблюдения',choices({0:'Наблюдение выключено',3:'Объект по координатам'})]},
    203:{x:['Спуск затвора',choices({0:'Не делать снимок',1:'Сделать снимок'})]},
    206:{param1:['Интервал съёмки',units('м')],param3:['Снимок при включении',choices({0:'Нет',1:'Да'})]},
  };
  return fields[command]?.[field]??[({x:'Параметр 5',y:'Параметр 6',z:'Параметр 7'})[field]??field.replace(/^param(\d+)$/,'Параметр $1'),numeric];
}

export function describeDifference(difference,downloaded=[],expected=[]) {
  if(difference.field==='count')return {title:'Количество команд, включая точку старта',planned:numeric(difference.expected),onboard:numeric(difference.actual)};
  const command=expected[difference.seq-1]?.command??downloaded.find(item=>item.seq===difference.seq)?.command;
  const [label,format]=fieldInfo(difference.field,command);
  const step=difference.seq===0?'Точка старта':`Шаг ${difference.seq??'—'}`;
  return {title:`${step}${commandInfo(command)?` · ${commandName(command)}`:''}: ${label.toLocaleLowerCase('ru-RU')}`,planned:format(difference.expected),onboard:format(difference.actual)};
}

export function explainBridgeError(message) {
  const homeDifference=message?.match(/^Плановый Home отличается от Home автопилота более чем на (.+) м$/);
  if(homeDifference)return `Точка старта в плане дальше ${homeDifference[1]} м от точки старта автопилота. Перед загрузкой миссии совместите их положения.`;
  if(message==='HEARTBEAT timeout')return 'Потерян сигнал связи от автопилота.';
  return message;
}
