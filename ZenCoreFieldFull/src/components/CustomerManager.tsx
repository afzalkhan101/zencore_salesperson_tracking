import React, {useRef,useState} from 'react';
import {ActivityIndicator,Pressable,StyleSheet,Text,TextInput,View} from 'react-native';
import {WebView} from 'react-native-webview';
import * as Odoo from '../services/odoo';

const MAP_HTML = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no"><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><style>html,body,#map{height:100%;margin:0}#tip{position:absolute;left:10px;right:10px;bottom:22px;background:#ffffffec;color:#174465;z-index:500;padding:9px;border-radius:10px;font:12px sans-serif;text-align:center;pointer-events:none}</style></head><body><div id="map"></div><div id="tip">Tap the map to select the customer location</div><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>(function(){if(!window.L){document.getElementById('tip').textContent='Map requires an internet connection';return}const map=L.map('map').setView([23.8103,90.4125],12);L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);let marker=null;window.setCustomerPin=function(lat,lng){if(!Number.isFinite(lat)||!Number.isFinite(lng))return;const ll=[lat,lng];if(marker)marker.setLatLng(ll);else marker=L.marker(ll,{draggable:true}).addTo(map).on('dragend',function(){const p=marker.getLatLng();window.ReactNativeWebView.postMessage(JSON.stringify({latitude:p.lat,longitude:p.lng}))});map.setView(ll,16)};map.on('click',function(e){window.setCustomerPin(e.latlng.lat,e.latlng.lng);window.ReactNativeWebView.postMessage(JSON.stringify({latitude:e.latlng.lat,longitude:e.latlng.lng}))});window.ReactNativeWebView.postMessage(JSON.stringify({ready:true}))})();</script></body></html>`;

type Form={name:string;phone:string;email:string;address:string;latitude:string;longitude:string};
const empty=():Form=>({name:'',phone:'',email:'',address:'',latitude:'',longitude:''});
const validCoordinate=(lat:number,lon:number)=>Number.isFinite(lat)&&Number.isFinite(lon)&&lat>=-90&&lat<=90&&lon>=-180&&lon<=180&&!(lat===0&&lon===0);
const textColor='#182D45';
export default function CustomerManager({onClose,onSaved}:{onClose:()=>void;onSaved?:()=>void}){
 const [screen,setScreen]=useState<'list'|'add'|'map'>('list');
 const [form,setForm]=useState<Form>(empty());
 const [customers,setCustomers]=useState<Odoo.CustomerRecord[]>([]);
 const [query,setQuery]=useState('');
 const [busy,setBusy]=useState(false);
 const [loaded,setLoaded]=useState(false);
 const [more,setMore]=useState(false);
 const [offset,setOffset]=useState(0);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [mapReady,setMapReady]=useState(false);
 const mapRef=useRef<WebView<{}>>(null);
 const lookupAt=useRef(0);
 const update=(key:keyof Form,value:string)=>setForm(f=>({...f,[key]:value}));
 const perform=async(fn:()=>Promise<void>)=>{if(busy)return;setBusy(true);setError('');setNotice('');try{await fn()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}};
 const load=async(next=false)=>{
  const from=next?offset:0;
  const p=await Odoo.findCustomers(query,from,40);
  setCustomers(items=>next?[...items,...p.partners.filter(c=>!items.some(x=>x.id===c.id))]:p.partners);
  setOffset(p.next_offset);setMore(p.has_more);setLoaded(true);
 };
 const lookup=async(mode:'address'|'coordinates')=>perform(async()=>{
  // Public Nominatim: one user-triggered lookup at a time, never keystroke autocomplete.
  if(Date.now()-lookupAt.current<1250)throw Error('Please allow a moment between location lookups.');
  lookupAt.current=Date.now();
  let url='';
  if(mode==='address'){
   if(form.address.trim().length<5)throw Error('Enter a detailed address before finding its coordinates.');
   url='https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q='+encodeURIComponent(form.address.trim());
  }else{
   const lat=Number(form.latitude),lon=Number(form.longitude);
   if(!form.latitude.trim()||!form.longitude.trim()||!validCoordinate(lat,lon))throw Error('Enter valid latitude and longitude.');
   url=`https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=18&lat=${lat}&lon=${lon}`;
  }
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),15000);
  let response:Response;
  try{response=await fetch(url,{headers:{'Accept':'application/json','Accept-Language':'en','User-Agent':'ZenCoreField/2.4 (Customer Location Lookup)'},signal:controller.signal})}finally{clearTimeout(timeout)}
  if(!response.ok)throw Error('Address lookup unavailable. Check internet or enter coordinates manually.');
  const value=await response.json();
  if(mode==='address'){
   const point=Array.isArray(value)?value[0]:null;
   if(!point||!validCoordinate(Number(point.lat),Number(point.lon)))throw Error('Location not found. Use Pick on Map or manual coordinates.');
   setForm(f=>({...f,latitude:String(point.lat),longitude:String(point.lon)}));
   setNotice('Coordinates located. Please verify the pin on the map before saving.');
  }else{
   if(!value?.display_name)throw Error('No address found for those coordinates. You may enter the address manually.');
   setForm(f=>({...f,address:String(value.display_name).slice(0,500)}));
   setNotice('Address found. Review and correct the street details if needed.');
  }
 });
 const save=()=>perform(async()=>{
  if(!form.name.trim())throw Error('Customer name is required.');
  if(!form.address.trim())throw Error('Customer address is required.');
  if(!form.latitude.trim()||!form.longitude.trim())throw Error('Select a location or enter latitude and longitude.');
  const lat=Number(form.latitude),lon=Number(form.longitude);
  if(!validCoordinate(lat,lon))throw Error('Latitude or longitude is invalid.');
  const data=await Odoo.createCustomer({name:form.name.trim(),phone:form.phone.trim(),email:form.email.trim(),address:form.address.trim(),latitude:lat,longitude:lon});
  setNotice(`${data.customer.name} saved in Odoo (ID ${data.customer.id}).`);setForm(empty());setScreen('list');setLoaded(false);setQuery('');
  try {const result=await Odoo.findCustomers('',0,40);
   setCustomers(result.partners);setOffset(result.next_offset);setMore(result.has_more);setLoaded(true);
  } catch {setNotice(`${data.customer.name} saved in Odoo. Refresh Customers to reload the list.`)}
  onSaved?.();
 });
 const input=(label:string,key:keyof Form,props?:{keyboardType?:'default'|'phone-pad'|'email-address'|'decimal-pad';placeholder?:string})=><View style={s.field} key={key}><Text style={s.label}>{label}</Text><TextInput style={s.input} value={form[key]} onChangeText={v=>update(key,v)} placeholder={props?.placeholder} placeholderTextColor="#9AABB8" keyboardType={props?.keyboardType||'default'} autoCapitalize={key==='email'?'none':'sentences'}/></View>;
 const action=(label:string,onPress:()=>void,light=false)=><Pressable disabled={busy} style={[s.button,light&&s.light,busy&&{opacity:.5}]} onPress={onPress}><Text style={[s.buttonText,light&&{color:'#07518C'}]}>{label}</Text></Pressable>;
 return <View style={s.wrapper}>
  <View style={s.heading}><Pressable onPress={()=>screen==='map'?setScreen('add'):screen==='add'?setScreen('list'):onClose()}><Text style={s.back}>‹ Back</Text></Pressable><Text style={s.title}>{screen==='list'?'Customers':screen==='add'?'Add Customer':'Pick Location'}</Text></View>
  {screen==='list'?<>
   <TextInput style={s.input} placeholder="Search customer name or phone" value={query} onChangeText={setQuery} placeholderTextColor="#9AABB8"/>
   <View style={s.horizontal}>{action('Search',()=>void perform(()=>load()))}{action('+ Add Customer',()=>{setForm(empty());setScreen('add');setError('');setNotice('')},true)}</View>
   {!loaded&&action('Load Customers',()=>void perform(()=>load()))}
   {loaded&&customers.length===0&&<Text style={s.note}>No customers found.</Text>}
   {customers.map(c=><View style={s.item} key={c.id}><Text style={s.name}>{c.name}</Text><Text style={s.note}>{[c.street,c.city].filter(Boolean).join(', ')||'No saved address'}</Text><Text style={s.note}>{c.phone||''}</Text></View>)}
   {more&&action('Load More',()=>void perform(()=>load(true)),true)}
  </>:screen==='add'?<>
    {input('Customer Name *','name')}
    {input('Phone','phone',{keyboardType:'phone-pad'})}
    {input('Email','email',{keyboardType:'email-address'})}
    {input('Address *','address',{placeholder:'House, road, area, city'})}
    {action('Find Coordinates from Address',()=>void lookup('address'),true)}
    <View style={s.horizontal}>{input('Latitude *','latitude',{keyboardType:'decimal-pad'})}{input('Longitude *','longitude',{keyboardType:'decimal-pad'})}</View>
    {action('Find Address from Coordinates',()=>void lookup('coordinates'),true)}
    {action('Pick Location on Map',()=>{setMapReady(false);setScreen('map')},true)}
    {action('Save Customer in Odoo',save)}
   </>:<>
    <Text style={s.note}>Tap or drag the marker to the customer location. Check the address before saving.</Text>
    <View style={s.mapWrap}><WebView<{}> ref={mapRef} source={{html:MAP_HTML}} javaScriptEnabled originWhitelist={['*']} domStorageEnabled onMessage={evt=>{
       try{const v=JSON.parse(evt.nativeEvent.data);if(v.ready){setMapReady(true);const lat=Number(form.latitude),lon=Number(form.longitude);if(form.latitude&&form.longitude&&validCoordinate(lat,lon))mapRef.current?.injectJavaScript(`window.setCustomerPin(${lat},${lon});true;`)}else if(validCoordinate(Number(v.latitude),Number(v.longitude))){setForm(f=>({...f,latitude:Number(v.latitude).toFixed(7),longitude:Number(v.longitude).toFixed(7)}))}}catch{}
    }}/></View>
    <Text style={s.note}>Selected: {form.latitude&&form.longitude?`${form.latitude}, ${form.longitude}`:'Tap the map to choose'}</Text>
    {action('Use This Location',()=>{if(!form.latitude||!form.longitude){setError('Select a pin on the map first.');return}setScreen('add');setNotice('Coordinates selected. You can find the address from these coordinates.')})}
   </>}
  {!!notice&&<Text style={s.success}>{notice}</Text>}
  {!!error&&<Text style={s.error}>{error}</Text>}
  {busy&&<ActivityIndicator color="#07518C"/>}
 </View>;
}
const s=StyleSheet.create({wrapper:{backgroundColor:'#fff',borderRadius:18,padding:15,borderColor:'#DFECE9',borderWidth:1,marginBottom:16},heading:{flexDirection:'row',alignItems:'center',gap:17,marginBottom:16},back:{fontWeight:'800',color:'#07518C',fontSize:13},title:{fontSize:18,fontWeight:'900',color:textColor},field:{flex:1,marginBottom:10,minWidth:120},label:{fontSize:12,color:'#577081',fontWeight:'700',marginBottom:6},input:{borderWidth:1,borderColor:'#D6E5E0',backgroundColor:'#F9FFFC',borderRadius:12,paddingHorizontal:12,paddingVertical:11,color:textColor,fontSize:13},horizontal:{flexDirection:'row',gap:9,marginVertical:8},button:{flex:1,backgroundColor:'#07518C',paddingVertical:12,paddingHorizontal:10,alignItems:'center',borderRadius:12,marginVertical:5},light:{backgroundColor:'#E8F8EE',borderWidth:1,borderColor:'#D0EBD5'},buttonText:{fontWeight:'800',color:'#fff',fontSize:12,textAlign:'center'},item:{paddingVertical:12,borderBottomWidth:1,borderBottomColor:'#E4EEEB'},name:{fontWeight:'800',color:textColor,fontSize:14},note:{color:'#6D8591',fontSize:12,lineHeight:19,marginVertical:5},mapWrap:{height:355,overflow:'hidden',borderRadius:15,marginVertical:12},error:{color:'#BD3544',fontSize:12,paddingVertical:8},success:{color:'#177640',fontSize:12,paddingVertical:8}});
