import React, {useEffect, useRef} from 'react';
import L from 'leaflet';
export default function Map({points,closed,onAdd,onMove,onSelect}) {
  const host = useRef(), map = useRef(), layer = useRef(), actions = useRef();
  actions.current = {onAdd,onMove,onSelect};
  useEffect(() => {
    map.current = L.map(host.current).setView([55.75,37.61],13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:19}).addTo(map.current);
    layer.current = L.layerGroup().addTo(map.current);
    map.current.on('click',event => actions.current.onAdd(event.latlng));
    const resize = new ResizeObserver(() => map.current.invalidateSize()); resize.observe(host.current);
    return () => { resize.disconnect(); map.current.remove(); };
  },[]);
  useEffect(() => {
    layer.current.clearLayers();
    const positions = points.map(point => [point.lat,point.lng]);
    if (closed && positions.length>1) positions.push(positions[0]);
    L.polyline(positions,{color:'#087f8c',weight:4,dashArray:'8 6'}).addTo(layer.current);
    points.forEach((point,index) => L.marker([point.lat,point.lng],{draggable:true,icon:L.divIcon({className:'waypoint',html:`<span>${index+1}</span>`,iconSize:[30,30],iconAnchor:[15,15]})}).addTo(layer.current).on('click',() => actions.current.onSelect(point.id)).on('dragend',event => actions.current.onMove(point.id,event.target.getLatLng())));
  },[points,closed]);
  return <div className="map" ref={host} aria-label="Карта: нажмите для добавления точки"/>;
}
