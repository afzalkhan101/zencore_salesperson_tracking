import React, {useEffect, useRef, useState} from 'react';
import {ActivityIndicator, Pressable, StyleSheet, Text, View} from 'react-native';
import {WebView} from 'react-native-webview';
import * as Location from 'expo-location';
import {cleanDisplayedRoute} from '../services/routeQuality';
import {getLastTrackingIdentity, getRecordedRoute, getTrackingIdentity, type RouteFix} from '../services/storage';

// No Google Maps key. Leaflet is loaded on demand over HTTPS while online.
// Map tiles are for interactive viewing only; this app never bulk-downloads tiles.
const HTML = `<!DOCTYPE html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin="anonymous" />
<style>html,body,#map{height:100%;width:100%;margin:0;background:#e8f4ed;font-family:sans-serif}#notice{position:absolute;top:12px;left:12px;right:12px;z-index:999;background:#fff;padding:10px;border-radius:9px;font-size:12px;color:#184a68;box-shadow:0 2px 8px #0001} .leaflet-control-attribution{font-size:10px!important}.zc-walker{background:transparent;border:0}.zc-walker-pin{width:36px;height:54px;display:block;background:transparent;border:0;filter:drop-shadow(0 1px 1px #1234)}.zc-walker-pin img{display:block;width:36px;height:54px;object-fit:contain}#zc-route-legend{position:absolute;bottom:27px;left:10px;z-index:500;display:flex;flex-direction:column;gap:7px;background:rgba(255,255,255,.95);border-radius:10px;padding:9px 11px;box-shadow:0 1px 8px #2342;pointer-events:none;font-size:11px;color:#24334d}#zc-route-legend .row{display:flex;align-items:center;gap:8px}#zc-route-legend .blue{width:28px;border-top:5px solid #0860F9;border-radius:5px}#zc-route-legend .dots{width:28px;border-top:5px dotted #F5B400}</style></head><body>
<div id="map"></div><div id="notice">Loading OpenStreetMap…</div><div id="zc-route-legend" style="display:none"><div class="row"><span class="blue"></span><span>Recorded GPS route</span></div><div class="row"><span class="dots"></span><span>Disconnected · no GPS</span></div></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin="anonymous"></script>
<script>
(function(){
 const tell=(type,message)=>window.ReactNativeWebView&&window.ReactNativeWebView.postMessage(JSON.stringify({type,message}));
 if(typeof L==='undefined'){document.getElementById('notice').textContent='Map library needs an internet connection.';tell('error','Leaflet failed to load');return;}
 const map=L.map('map',{zoomControl:true,attributionControl:true}).setView([0,0],2);
 L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);
 const lines=L.layerGroup().addTo(map);
 let last=null,first=null,target=null,initial=true,following=true;
 map.on('dragstart',()=>{following=false});
 const dot=(latlng,color)=>L.circleMarker(latlng,{radius:9,color:'#fff',weight:3,fillColor:color,fillOpacity:1}).addTo(map);
 const gapMeters=(a,b)=>{const rad=x=>x*Math.PI/180;const dLat=rad(b.latitude-a.latitude),dLon=rad(b.longitude-a.longitude);const h=Math.sin(dLat/2)**2+Math.cos(rad(a.latitude))*Math.cos(rad(b.latitude))*Math.sin(dLon/2)**2;return 6371000*2*Math.atan2(Math.sqrt(h),Math.sqrt(Math.max(0,1-h)));};
 const walker=(latlng)=>L.marker(latlng,{icon:L.divIcon({className:'zc-walker',html:'<div class="zc-walker-pin"><img src="data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2048%2072%22%20width%3D%2248%22%20height%3D%2272%22%20role%3D%22img%22%20aria-label%3D%22Walking%20salesperson%20carrying%20a%20small%20briefcase%22%3E%0A%20%20%3Cdefs%3E%3Cfilter%20id%3D%22sh%22%20x%3D%22-40%25%22%20y%3D%22-30%25%22%20width%3D%22180%25%22%20height%3D%22170%25%22%3E%3CfeGaussianBlur%20stdDeviation%3D%221.1%22%2F%3E%3C%2Ffilter%3E%3C%2Fdefs%3E%0A%20%20%3Cellipse%20cx%3D%2223%22%20cy%3D%2268%22%20rx%3D%2214%22%20ry%3D%222.1%22%20fill%3D%22%2316243A%22%20opacity%3D%22.19%22%20filter%3D%22url%28%23sh%29%22%2F%3E%0A%20%20%3Cg%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%0A%20%20%20%20%3C%21--%20Back%20walking%20leg%20and%20shoe%20--%3E%0A%20%20%20%20%3Cpath%20d%3D%22M21%2040%20L16%2052%20L9%2060%22%20stroke%3D%22%23243B55%22%20stroke-width%3D%225%22%20fill%3D%22none%22%2F%3E%0A%20%20%20%20%3Cpath%20d%3D%22M9%2060%20L5%2062%20L12%2063%22%20stroke%3D%22%23182736%22%20stroke-width%3D%223.6%22%20fill%3D%22none%22%2F%3E%0A%20%20%20%20%3C%21--%20Front%20walking%20leg%20and%20shoe%20--%3E%0A%20%20%20%20%3Cpath%20d%3D%22M27%2040%20L29%2052%20L38%2060%22%20stroke%3D%22%23203850%22%20stroke-width%3D%225.2%22%20fill%3D%22none%22%2F%3E%0A%20%20%20%20%3Cpath%20d%3D%22M38%2060%20L43%2062%20L35%2063%22%20stroke%3D%22%23172B42%22%20stroke-width%3D%223.6%22%20fill%3D%22none%22%2F%3E%0A%20%20%20%20%3C%21--%20Body%2C%20green%20field%20uniform%20--%3E%0A%20%20%20%20%3Cpath%20d%3D%22M17%2018%20Q23%2015%2030%2018%20L32%2039%20L19%2042%20L15%2028%20Z%22%20fill%3D%22%2319AA52%22%20stroke%3D%22%2308733E%22%20stroke-width%3D%221.3%22%2F%3E%0A%20%20%20%20%3Cpath%20d%3D%22M23%2019%20L26%2024%22%20stroke%3D%22%23BBF7D0%22%20stroke-width%3D%221.7%22%2F%3E%0A%20%20%20%20%3C%21--%20Rear%20arm%20moving%20behind%20body%20--%3E%0A%20%20%20%20%3Cpath%20d%3D%22M18%2023%20L12%2033%20L8%2037%22%20fill%3D%22none%22%20stroke%3D%22%23B6764B%22%20stroke-width%3D%223.9%22%2F%3E%0A%20%20%20%20%3Cpath%20d%3D%22M8%2037%20L6%2039%22%20fill%3D%22none%22%20stroke%3D%22%23E0A477%22%20stroke-width%3D%222.9%22%2F%3E%0A%20%20%20%20%3C%21--%20Face%20and%20hair%20--%3E%0A%20%20%20%20%3Cpath%20d%3D%22M21%206%20Q29%203%2031%2011%20Q32%2017%2026%2019%20Q19%2018%2019%2012%20Z%22%20fill%3D%22%23DE9B6B%22%20stroke%3D%22%23754A31%22%20stroke-width%3D%22.7%22%2F%3E%0A%20%20%20%20%3Cpath%20d%3D%22M19%2012%20Q18%204%2023%203%20Q30%201%2033%208%20L31%2012%20L28%207%20L24%208%20L20%2014%20Z%22%20fill%3D%22%23162D40%22%2F%3E%0A%20%20%20%20%3Cpath%20d%3D%22M30%2012%20L33%2014%20L29%2015%22%20fill%3D%22%23D68A5D%22%2F%3E%0A%20%20%20%20%3C%21--%20Front%20arm%20reaches%20down%20to%20SMALL%20hand-held%20bag%20--%3E%0A%20%20%20%20%3Cpath%20d%3D%22M30%2022%20L35%2033%20L34%2043%22%20fill%3D%22none%22%20stroke%3D%22%23D99260%22%20stroke-width%3D%223.7%22%2F%3E%0A%20%20%20%20%3Ccircle%20cx%3D%2234%22%20cy%3D%2243%22%20r%3D%221.9%22%20fill%3D%22%23E4A476%22%2F%3E%0A%20%20%20%20%3C%21--%20Briefcase%20is%20~8%20x%206px%20versus%2060px%20figure%20height%20--%3E%0A%20%20%20%20%3Cpath%20d%3D%22M32%2046%20V43.7%20Q32%2041.9%2034%2041.9%20Q36%2041.9%2036%2043.7%20V46%22%20fill%3D%22none%22%20stroke%3D%22%2353351F%22%20stroke-width%3D%221.1%22%2F%3E%0A%20%20%20%20%3Crect%20x%3D%2230%22%20y%3D%2245%22%20width%3D%229%22%20height%3D%227%22%20rx%3D%221.2%22%20fill%3D%22%2398602F%22%20stroke%3D%22%2356351E%22%20stroke-width%3D%22.9%22%2F%3E%0A%20%20%20%20%3Cpath%20d%3D%22M30.8%2048.2%20H38.2%22%20stroke%3D%22%23BB8449%22%20stroke-width%3D%22.8%22%2F%3E%0A%20%20%20%20%3Crect%20x%3D%2233.7%22%20y%3D%2247.4%22%20width%3D%221.6%22%20height%3D%221.6%22%20rx%3D%22.3%22%20fill%3D%22%23E8C780%22%2F%3E%0A%20%20%3C%2Fg%3E%0A%3C%2Fsvg%3E" alt="Salesperson holding small briefcase" /></div>',iconSize:[36,54],iconAnchor:[18,50]})}).addTo(map);
 window.updateZenCoreMap=function(payload){
  try{
   const points=Array.isArray(payload.points)?payload.points.filter(p=>Number.isFinite(p.latitude)&&Number.isFinite(p.longitude)&&Math.abs(p.latitude)<=90&&Math.abs(p.longitude)<=180):[];
   const segments=Array.isArray(payload.segments)?payload.segments:[];
   lines.clearLayers();
   const legend=document.getElementById('zc-route-legend');
   let hasVisibleGap=false;
   const coords=points.map(p=>[p.latitude,p.longitude]);
   // Gaps are display-only connectors; never add them to measured GPS distance.
   // Up to and including 500 m: solid blue. Greater than 500 m: amber dots.
   segments.forEach((s,i)=>{
    if(s.length>=2)L.polyline(s.map(p=>[p.latitude,p.longitude]),{color:'#0860F9',weight:8,opacity:.95,lineCap:'round',lineJoin:'round'}).addTo(lines);
    if(i>0&&segments[i-1].length&&s.length){
     const a=segments[i-1][segments[i-1].length-1],b=s[0];
     const isLongGap=gapMeters(a,b)>500.001;
     const style=isLongGap
      ? {color:'#F5B400',weight:5,opacity:.9,dashArray:'1 11',lineCap:'round',lineJoin:'round',interactive:true}
      : {color:'#0860F9',weight:8,opacity:.95,lineCap:'round',lineJoin:'round',interactive:true};
     if(isLongGap)hasVisibleGap=true;
     L.polyline([[a.latitude,a.longitude],[b.latitude,b.longitude]],style)
      .bindTooltip('GPS recording gap — straight-line estimate; actual travel path unknown').addTo(lines);
    }
   });
   if(legend)legend.style.display=hasVisibleGap?'flex':'none';
   if(first){map.removeLayer(first);first=null}if(last){map.removeLayer(last);last=null}if(target){map.removeLayer(target);target=null}
   if(coords.length){first=dot(coords[0],'#70BF36');}
   const live=payload.current&&Number.isFinite(payload.current.latitude)&&Number.isFinite(payload.current.longitude)
      ?[payload.current.latitude,payload.current.longitude]:(coords.length?coords[coords.length-1]:null);
   if(live){last=walker(live);}
   if(payload.destination&&Number.isFinite(payload.destination.latitude)&&Number.isFinite(payload.destination.longitude)){
      target=dot([payload.destination.latitude,payload.destination.longitude],'#32a852');
   }
   const notice=document.getElementById('notice');
   if(live||coords.length){notice.style.display='none';}else{notice.style.display='block';notice.textContent='Waiting for location. Open a Visit Plan to record a route.';}
   if(initial){if(coords.length>1){map.fitBounds(L.latLngBounds(coords).pad(.25),{maxZoom:16});initial=false;}
     else if(live){map.setView(live,15);initial=false;}}
   else if(live&&following){map.panTo(live,{animate:false});}
   tell('updated',String(points.length));
  }catch(err){tell('error',String(err));}
 };
 tell('ready','Leaflet ready');
})();
</script></body></html>`;

type Point={latitude:number;longitude:number};
export default function LiveRouteMap({active,online,destination}:{active:boolean;online:boolean|null;destination?:Point|null}){
 const view=useRef<WebView<{}>>(null);
 const [route,setRoute]=useState<RouteFix[]>([]);
 const [current,setCurrent]=useState<Point|null>(null);
 const [ready,setReady]=useState(false);
 const [error,setError]=useState('');
 const [planId,setPlanId]=useState<number|null>(null);
 const [isLive,setIsLive]=useState(false);
 useEffect(()=>{
  let alive=true;
  const poll=async()=>{
   try{
    const running=await getTrackingIdentity();
    const identity=running||await getLastTrackingIdentity();
    const points=await getRecordedRoute(identity);
    if(!alive)return;
    setRoute(points);setPlanId(identity?.planId??null);setIsLive(Boolean(running));
    const permission=await Location.getForegroundPermissionsAsync();
    if(permission.granted){
      const pos=await Location.getCurrentPositionAsync({accuracy:Location.Accuracy.High}).catch(()=>null);
      if(pos&&alive&&pos.coords.accuracy!=null&&pos.coords.accuracy<=35)setCurrent({latitude:pos.coords.latitude,longitude:pos.coords.longitude});
    }
   }catch(e){if(alive)setError(e instanceof Error?e.message:String(e));}
  };
  void poll();const timer=setInterval(()=>{void poll()},10000);
  return()=>{alive=false;clearInterval(timer)};
 },[active]);
 useEffect(()=>{
  if(!ready)return;
  const segments=cleanDisplayedRoute(route);
  const recorded=segments.flat();
  // Do not substitute a fresh phone fix for the last recorded salesperson
  // position when tracking is stopped; this marker represents the GPS log.
  const payload={points:recorded,segments,current:recorded.length?null:(isLive?current:null),destination};
  view.current?.injectJavaScript(`window.updateZenCoreMap && window.updateZenCoreMap(${JSON.stringify(payload)});true;`);
 },[ready,route,current,destination]);
 return <View>
  <View style={styles.frame}>
   <WebView<{}> ref={view} source={{html:HTML}}
    originWhitelist={['*']} javaScriptEnabled domStorageEnabled
    mixedContentMode="never" setSupportMultipleWindows={false}
    cacheEnabled
    userAgent="ZenCoreField/2.2 (ReactNativeWebView; interactive map)"
    onMessage={event=>{try{const msg=JSON.parse(event.nativeEvent.data);if(msg.type==='ready'){setReady(true);setError('')}else if(msg.type==='error'){setError(msg.message)}}catch{}}}
    onError={e=>setError(e.nativeEvent.description||'Map WebView failed')}
    style={styles.web}
   />
   {!ready&&<View style={styles.loading}><ActivityIndicator color="#07518C"/><Text style={styles.hint}>Loading Leaflet map…</Text></View>}
  </View>
  
  <Text style={styles.status}>{isLive?'Tracking active':planId?`Plan #${planId}`:'No recorded route'}</Text>
  
  {Boolean(error)&&<Text style={styles.error}>{error}</Text>}
  
 </View>;
}
const styles=StyleSheet.create({
 frame:{height:350,borderRadius:18,overflow:'hidden',backgroundColor:'#e9f5ee',borderWidth:1,borderColor:'#d9e8e2'},
 web:{flex:1,backgroundColor:'#e9f5ee'},
 loading:{position:'absolute',left:0,right:0,top:0,bottom:0,alignItems:'center',justifyContent:'center',backgroundColor:'#e9f5ee'},
 hint:{fontSize:11,lineHeight:17,color:'#627985',marginTop:9},
 error:{fontSize:12,color:'#b02a37',marginTop:7},
 status:{fontSize:12,fontWeight:'700',color:'#124966',marginTop:8},
 legend:{flexDirection:'row',justifyContent:'space-between',marginTop:10},
 blue:{fontSize:11,color:'#07518C'},green:{fontSize:11,color:'#288b43'},
});
