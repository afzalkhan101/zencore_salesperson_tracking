import type {RouteFix} from './storage';
// View-only filtering. Raw GPS points and sync acknowledgements are never altered.
const rad=(x:number)=>x*Math.PI/180;
export function haversineMeters(a:RouteFix,b:RouteFix){
 const dLat=rad(b.latitude-a.latitude),dLon=rad(b.longitude-a.longitude);
 const h=Math.sin(dLat/2)**2+Math.cos(rad(a.latitude))*Math.cos(rad(b.latitude))*Math.sin(dLon/2)**2;
 return 6371000*2*Math.atan2(Math.sqrt(h),Math.sqrt(Math.max(0,1-h)));
}
export function cleanDisplayedRoute(points:RouteFix[]):RouteFix[][]{
 const ordered=[...points].sort((a,b)=>a.capturedAt-b.capturedAt);
 const preliminary:RouteFix[]=[];
 for(const point of ordered){
  if(!Number.isFinite(point.latitude)||!Number.isFinite(point.longitude)||Math.abs(point.latitude)>90||Math.abs(point.longitude)>180||!Number.isFinite(point.accuracy)||point.accuracy<0||point.accuracy>35||!Number.isFinite(point.capturedAt))continue;
  const prev=preliminary[preliminary.length-1];
  if(prev){
   const dt=(point.capturedAt-prev.capturedAt)/1000;
   if(dt<=0)continue;
   const delta=haversineMeters(prev,point);
   // Reject location jitter, particularly stationary GPS wander.
   if(delta<Math.max(22,1.25*(point.accuracy+prev.accuracy)))continue;
   // GPS teleports: 22m/s ~79km/h; keep raw fix for diagnostics, not map.
   if(dt<=180&&delta/dt>22)continue;
  }
  preliminary.push(point);
 }
 // Detect isolated triangular spikes that return close to the prior location.
 const stable:RouteFix[]=[];
 for(let i=0;i<preliminary.length;i++){
  const prior=stable[stable.length-1],current=preliminary[i],next=preliminary[i+1];
  if(prior&&next){
   const back=haversineMeters(prior,next);
   const outward=haversineMeters(prior,current);
   const returnDist=haversineMeters(current,next);
   const duration=(next.capturedAt-prior.capturedAt)/1000;
   if(duration>0&&duration<150&&outward>80&&returnDist>80&&back<Math.max(40,outward*0.28))continue;
  }
  stable.push(current);
 }
 const segments:RouteFix[][]=[];let segment:RouteFix[]=[];
 for(const point of stable){
  const prev=segment[segment.length-1];
  if(prev){const seconds=(point.capturedAt-prev.capturedAt)/1000;
   if(seconds>240||haversineMeters(prev,point)/Math.max(1,seconds)>22){if(segment.length)segments.push(segment);segment=[];}
  }
  segment.push(point);
 }
 if(segment.length)segments.push(segment);
 return segments;
}
