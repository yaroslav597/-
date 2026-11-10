import React, {useEffect,useRef} from 'react';
import L from 'leaflet';
import {flightPath} from '../domain/mission.js';
export default function Map({points,settings,vehicle,track=[],currentItem,reachedItems=[],onAdd,onMove,onSelect,onMoveLocation,onMoveRoi}) {
  const host=useRef(),map=useRef(),layer=useRef(),vehicleLayer=useRef(),actions=useRef();
  actions.current={onAdd,onMove,onSelect,onMoveLocation,onMoveRoi};
  useEffect(()=>{
    map.current=L.map(host.current).setView([settings.home.lat,settings.home.lng],13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:19}).addTo(map.current);
    layer.current=L.layerGroup().addTo(map.current);vehicleLayer.current=L.layerGroup().addTo(map.current);
    map.current.on('click',event=>actions.current.onAdd(event.latlng));
    const resize=new ResizeObserver(()=>map.current.invalidateSize());resize.observe(host.current);
    return ()=>{resize.disconnect();map.current.remove();};
  },[]);
  useEffect(()=>{
    layer.current.clearLayers();
    L.polyline(flightPath(points,settings).map(point=>[point.lat,point.lng]),{color:'#087f8c',weight:4,dashArray:'8 6',className:'flight-path'}).addTo(layer.current);
    function marker(location,text,className,title,onDrag,onClick) {
      const item=L.marker([location.lat,location.lng],{title,draggable:true,icon:L.divIcon({className:`waypoint ${className}`,html:`<span>${text}</span>`,iconSize:[30,30],iconAnchor:[15,15]})}).addTo(layer.current).bindTooltip(title);
      if(onClick)item.on('click',onClick);
      item.on('dragend',event=>onDrag(event.target.getLatLng()));
    }
    points.forEach((point,index)=>{
      const matches=item=>item&&[16,19].includes(item.command)&&Math.abs(item.x/1e7-point.lat)<0.0000002&&Math.abs(item.y/1e7-point.lng)<0.0000002;
      const progress=matches(currentItem)?'current-point':reachedItems.some(matches)?'reached-point':'';
      marker(point,index+1,progress,`Точка ${index+1} · действий: ${point.actions.length}`,position=>actions.current.onMove(point.id,position),()=>actions.current.onSelect(point.id));
      point.actions.filter(action=>action.command===201).forEach(action=>{
        marker(action.target,'◎','roi-marker',`ROI точки ${index+1}`,position=>actions.current.onMoveRoi(point.id,action.id,position),()=>actions.current.onSelect(point.id));
        L.polyline([[point.lat,point.lng],[action.target.lat,action.target.lng]],{color:'#e9be76',weight:1,dashArray:'3 8',className:'roi-link'}).addTo(layer.current);
      });
    });
    marker(settings.home,'H','home-marker','Home · место старта',position=>actions.current.onMoveLocation('home',position));
    if(settings.ending==='land')marker(settings.landing,'L','land-marker','Место посадки',position=>actions.current.onMoveLocation('landing',position));
  },[points,settings,currentItem,reachedItems]);
  useEffect(()=>{
    vehicleLayer.current.clearLayers();
    if(track.length>1)L.polyline(track.map(point=>[point.lat,point.lng]),{color:'#54df95',weight:3,className:'actual-track'}).addTo(vehicleLayer.current);
    if(vehicle)L.marker([vehicle.lat,vehicle.lng],{interactive:false,icon:L.divIcon({className:'waypoint vehicle-marker',html:'<span>✥</span>',iconSize:[30,30],iconAnchor:[15,15]})}).addTo(vehicleLayer.current);
  },[vehicle,track]);
  return <div className="map" ref={host} aria-label="Карта маршрута, Home и объектов наблюдения"/>;
}
