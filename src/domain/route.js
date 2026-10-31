import distance from '@turf/distance';
export const meters = (first, second) => distance([first.lng, first.lat], [second.lng, second.lat], {units:'kilometers'}) * 1000;
export function length(points, closed = false) {
  return points.reduce((total, point, index) => total + (index ? meters(points[index-1], point) : 0), 0) + (closed && points.length > 1 ? meters(points.at(-1), points[0]) : 0);
}
export function validPoint(point) { return Number.isFinite(point.lat) && Math.abs(point.lat)<=90 && Number.isFinite(point.lng) && Math.abs(point.lng)<=180 && Number.isFinite(point.alt) && point.alt>=5 && point.alt<=500; }
