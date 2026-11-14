/** Route preview: address lookup is initiated after address entry, never autocomplete. */
export type RoadDistance = {km:number; fromLabel:string; toLabel:string};
const addressCache = new Map<string,{lat:number;lon:number;label:string}>();
const distanceCache = new Map<string,RoadDistance>();
let previousGeocodeAt=0;
const sleep=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
const normalize=(s:string)=>s.trim().replace(/\s+/g,' ').toLowerCase();
async function getJson(url:string, timeout=12000):Promise<any>{
 const ctrl=new AbortController();const timer=setTimeout(()=>ctrl.abort(),timeout);
 try{const res=await fetch(url,{signal:ctrl.signal,headers:{Accept:'application/json','User-Agent':'ZenCoreField/2.1 (Mobile Visit Planning)'}});if(!res.ok)throw Error(`Route service HTTP ${res.status}`);return await res.json();}
 finally{clearTimeout(timer)}
}
async function geocode(address:string){
 const key=normalize(address);const cached=addressCache.get(key);if(cached)return cached;
 // Public Nominatim: only user-triggered lookup, serialized and throttled to <= 1 req/sec.
 // For deployment with many field agents, replace with a managed or self-hosted provider.
 const delay=Math.max(0,1200-(Date.now()-previousGeocodeAt));if(delay)await sleep(delay);
 previousGeocodeAt=Date.now();
 const endpoint=process.env.EXPO_PUBLIC_ZC_GEOCODE_URL||'https://nominatim.openstreetmap.org/search';
 const url=`${endpoint}?format=json&limit=1&q=${encodeURIComponent(address)}`;
 const data=await getJson(url);if(!Array.isArray(data)||!data.length)throw Error(`Address not found: ${address}`);
 const lat=Number(data[0].lat),lon=Number(data[0].lon);
 if(!Number.isFinite(lat)||!Number.isFinite(lon))throw Error('Invalid geocoding result');
 const result={lat,lon,label:String(data[0].display_name||address)};addressCache.set(key,result);return result;
}
export async function calculateRoadKm(from:string,to:string):Promise<RoadDistance>{
 if(!from.trim()||!to.trim())throw Error('Enter both addresses');
 const key=`${normalize(from)}|${normalize(to)}`;const cached=distanceCache.get(key);if(cached)return cached;
 const a=await geocode(from),b=await geocode(to);
 const endpoint=(process.env.EXPO_PUBLIC_ZC_ROUTING_URL||'https://router.project-osrm.org/route/v1/driving').replace(/\/$/,'');
 const result=await getJson(`${endpoint}/${a.lon},${a.lat};${b.lon},${b.lat}?overview=false&steps=false`,15000);
 const meters=Number(result?.routes?.[0]?.distance);
 if(result?.code!=='Ok'||!Number.isFinite(meters)||meters<0)throw Error('Road route not available for these addresses');
 const answer={km:Math.round(meters/10)/100,fromLabel:a.label,toLabel:b.label};distanceCache.set(key,answer);return answer;
}
