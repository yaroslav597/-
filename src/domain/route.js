import distance from '@turf/distance';
export const meters = (first, second) => distance([first.lng, first.lat], [second.lng, second.lat], {units:'kilometers'}) * 1000;
export function length(points, closed = false) {
  return points.reduce((total, point, index) => total + (index ? meters(points[index-1], point) : 0), 0) + (closed && points.length > 1 ? meters(points.at(-1), points[0]) : 0);
}
export function optimize(points, closed = false) {
  if (points.length < 3) return [...points];
  const remaining = points.slice(1), route = [points[0]];
  while (remaining.length) {
    let best = 0;
    remaining.forEach((point,index) => { if (meters(route.at(-1),point) < meters(route.at(-1),remaining[best])) best = index; });
    route.push(remaining.splice(best,1)[0]);
  }
  let improved = true;
  while (improved) {
    improved = false;
    for (let start = 1; start < route.length-1; start++) for (let end = start+1; end < route.length; end++) {
      const candidate = [...route.slice(0,start), ...route.slice(start,end+1).reverse(), ...route.slice(end+1)];
      if (length(candidate,closed) + 0.001 < length(route,closed)) { route.splice(0,route.length,...candidate); improved = true; }
    }
  }
  return length(route,closed) < length(points,closed) ? route : [...points];
}
export function validPoint(point) { return Number.isFinite(point.lat) && Math.abs(point.lat)<=90 && Number.isFinite(point.lng) && Math.abs(point.lng)<=180 && Number.isFinite(point.alt) && point.alt>=5 && point.alt<=500; }
