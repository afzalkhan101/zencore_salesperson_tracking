import React, {useCallback, useEffect, useState} from 'react';
import {ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View} from 'react-native';
import * as Location from 'expo-location';
import type {Customer, Plan, Target} from '../types/models';
import * as Odoo from '../services/odoo';
import {getRoadRouteForPoints,reverseLocation,type RoadRoute,type TravelMode} from '../services/routeDistance';
import LocationPicker from './LocationPicker';
import RoutePreviewMap from './RoutePreviewMap';
import {C} from '../theme/colors';

type Employee = {id:number;name:string};
type Step = 0|1|2|3;
type Props = {plan:Plan; salesperson:string; onChange:(update:Partial<Plan>)=>void; onSave:()=>void; onSubmit:()=>void; onCancel:()=>void; busy:boolean;onMapInteractionChange?:(active:boolean)=>void};
const PURPOSES=[['followup','Follow Up'],['order','New Order'],['payment','Payment Collection'],['complaint','Complaint Resolution'],['demo','Product Demo']];
const TRAVEL_MODES:{value:TravelMode;label:string;icon:string}[]=[{value:'walk',label:'Walk',icon:'🚶'},{value:'bike',label:'Bike',icon:'🚲'},{value:'car',label:'Car',icon:'🚗'}];
const uid=()=>`${Date.now()}-${Math.random().toString(36).slice(2)}`;
const newTarget=():Target=>({id:uid(),customer:'',customerIds:[],customerNames:[],employeeIds:[],employeeNames:[],from:'',to:'',km:0,notes:''});
const number=(v:string)=>Number.isFinite(Number(v))?Math.max(0,Number(v)):0;
const price=(v:number)=>`BDT ${Number(v||0).toFixed(2)}`;
function Caption({children}:{children:React.ReactNode}){return <Text style={styles.caption}>{children}</Text>}
function Control({label,value,onChange,placeholder,numeric=false}:{label:string;value:string;onChange:(v:string)=>void;placeholder?:string;numeric?:boolean}){
 if(label==='Expected KM')return <View style={{marginBottom:14}}><Text style={styles.label}>Total Distance</Text><View style={styles.calculatedDistance}><Text style={styles.calculatedDistanceText}>{Number(value)>0?`${Number(value).toFixed(2)} KM`:'Calculating automatically…'}</Text></View></View>;
 return <View style={{marginBottom:14}}><Text style={styles.label}>{label}</Text><TextInput style={styles.input} value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor="#94A3B8" keyboardType={numeric?'decimal-pad':'default'}/></View>
}
function Action({title,onPress,secondary=false,disabled=false}:{title:string;onPress:()=>void;secondary?:boolean;disabled?:boolean}){
 if(title==='Recalculate Road KM'||title==='Calculating distance…')return null;
 return <Pressable onPress={onPress} disabled={disabled} style={[styles.action,secondary&&styles.secondary,disabled&&{opacity:.4}]}><Text style={[styles.actionText,secondary&&{color:C.blue}]}>{title}</Text></Pressable>
}
function Panel({children}:{children:React.ReactNode}){return <View style={styles.panel}>{children}</View>}
export default function VisitPlanEditor({plan,salesperson,onChange,onSave,onSubmit,onCancel,busy,onMapInteractionChange}:Props){
 const [step,setStep]=useState<Step>(0);
 const [target,setTarget]=useState<Target>(newTarget());
 const [editIndex,setEditIndex]=useState<number|null>(null);
 const [picker,setPicker]=useState<'customers'|'employees'|null>(null);
 const [query,setQuery]=useState('');
 const [customers,setCustomers]=useState<Customer[]>([]);
 const [employees,setEmployees]=useState<Employee[]>([]);
 const [offset,setOffset]=useState(0);
 const [more,setMore]=useState(false);
 const [loading,setLoading]=useState(false);
 const [loadError,setLoadError]=useState('');
 const [routeBusy,setRouteBusy]=useState(false);
 const [routeError,setRouteError]=useState('');
 const [routePreview,setRoutePreview]=useState<RoadRoute|null>(null);
 const [travelMode,setTravelMode]=useState<TravelMode>('car');
 const [capturingCurrentLocation,setCapturingCurrentLocation]=useState(false);
 const [currentLocationAccuracy,setCurrentLocationAccuracy]=useState<number|null>(null);
 const [locationPicker,setLocationPicker]=useState(false);
 const routeAttempt=React.useRef(0);
 const resolveKm=async()=>{
  const customer=customers.find(c=>c.id===(target.customerIds||[])[0]);
  if(!target.from.trim()||!customer||customer.latitude==null||customer.longitude==null||target.fromLatitude==null||target.fromLongitude==null){setRoutePreview(null);return}
  const attempt=++routeAttempt.current;setRouteBusy(true);setRouteError('');
  try{const result=await getRoadRouteForPoints({latitude:target.fromLatitude,longitude:target.fromLongitude,label:target.from},{latitude:customer.latitude,longitude:customer.longitude,label:customer.name},travelMode);
   if(attempt===routeAttempt.current){setTarget(old=>({...old,km:result.km}));setRoutePreview(result)}
  }catch(err){if(attempt===routeAttempt.current)setRouteError(err instanceof Error?err.message:'Unable to calculate distance');}
  finally{if(attempt===routeAttempt.current)setRouteBusy(false);}
 };
 // Route distance is calculated as soon as both endpoints are known. The
 // salesperson never needs to enter or recalculate kilometres manually.
 useEffect(()=>{
  const customer=customers.find(c=>c.id===(target.customerIds||[])[0]);
  if(!target.from.trim()||!customer||customer.latitude==null||customer.longitude==null||target.fromLatitude==null||target.fromLongitude==null)return;
  void resolveKm();
 },[target.from,target.fromLatitude,target.fromLongitude,target.customerIds,customers,travelMode]);
 const patchTarget=(v:Partial<Target>)=>setTarget(old=>({...old,...v}));
 const useCurrentLocation=async()=>{
  if(capturingCurrentLocation)return;
  setCapturingCurrentLocation(true);setRouteError('');
  try{
   const permission=await Location.requestForegroundPermissionsAsync();
   if(permission.status!=='granted')throw Error('Location permission is required to use your current location. You can still search on the map.');
   const position=await Location.getCurrentPositionAsync({accuracy:Location.Accuracy.High,mayShowUserSettingsDialog:true});
   const latitude=position.coords.latitude,longitude=position.coords.longitude;
   if(!Number.isFinite(latitude)||!Number.isFinite(longitude))throw Error('Current GPS location is unavailable. Try again outdoors or choose it on the map.');
   const point=await reverseLocation(latitude,longitude).catch(()=>({latitude,longitude,label:`Lat ${latitude.toFixed(6)}, Lng ${longitude.toFixed(6)}`}));
   routeAttempt.current++;setRoutePreview(null);setCurrentLocationAccuracy(position.coords.accuracy);patchTarget({from:point.label,fromLatitude:latitude,fromLongitude:longitude,km:0});
  }catch(error){setRouteError(error instanceof Error?error.message:'Unable to capture your current location.');}
  finally{setCapturingCurrentLocation(false)}
 };
 const load=useCallback(async(q:string,start:number,kind:'customers'|'employees')=>{
  setLoading(true);setLoadError('');
  try {
   if(kind==='customers'){
    const res=await Odoo.findCustomers(q,start,50);
    setCustomers(old=>start===0?res.partners:[...old,...res.partners.filter(item=>!old.some(other=>other.id===item.id))]);
    setMore(res.has_more);setOffset(res.next_offset);
   } else {
    const res=await Odoo.findEmployees(q,start,50);
    setEmployees(old=>start===0?res.employees:[...old,...res.employees.filter(item=>!old.some(other=>other.id===item.id))]);
    setMore(res.has_more);setOffset(res.next_offset);
   }
  }catch(e){setLoadError(e instanceof Error?e.message:String(e))}finally{setLoading(false)}
 },[]);
 useEffect(()=>{
  if(!picker)return;
  const timer=setTimeout(()=>{void load(query,0,picker)},query?350:0);
  return()=>clearTimeout(timer);
 },[picker,query,load]);
 const toggleCustomer=(c:Customer)=>{
  setRoutePreview(null);
  const ids=target.customerIds||[];
  const names=target.customerNames||[];
  if(ids.includes(c.id))patchTarget({customerIds:ids.filter(id=>id!==c.id),customerNames:names.filter((_,i)=>ids[i]!==c.id)});
  else patchTarget({customerIds:[...ids,c.id],customerNames:[...names,c.name]});
 };
 const toggleEmployee=(e:Employee)=>{
  const ids=target.employeeIds||[];
  const names=target.employeeNames||[];
  if(ids.includes(e.id))patchTarget({employeeIds:ids.filter(id=>id!==e.id),employeeNames:names.filter((_,i)=>ids[i]!==e.id)});
  else patchTarget({employeeIds:[...ids,e.id],employeeNames:[...names,e.name]});
 };
 const saveTarget=()=>{
  if(!(target.customerIds||[]).length){Alert.alert('Customer required','Select at least one Odoo customer.');return}
  if(!target.from.trim()||target.fromLatitude==null||target.fromLongitude==null){Alert.alert('From location required','Choose From Location from the map or enter latitude and longitude.');return}
  if((target.km||0)<0){Alert.alert('Invalid value','KM cannot be negative.');return}
  const chosen=target.customerIds||[];
  const updated:Target={...target,customerId:chosen[0],customer:(target.customerNames||[]).join(', ')};
  const arr=[...plan.targets];if(editIndex===null)arr.push(updated);else arr[editIndex]=updated;
  onChange({targets:arr});setEditIndex(null);setRoutePreview(null);setTarget(newTarget());
 };
 const edit=(i:number)=>{routeAttempt.current++;setRouteError('');setRoutePreview(null);setCurrentLocationAccuracy(null);setTarget({...plan.targets[i]});setEditIndex(i)};
 const valid=()=>{
  if(!/^\d{4}-\d{2}-\d{2}$/.test(plan.date)){Alert.alert('Invalid visit date','Enter the visit date as YYYY-MM-DD.');return false}
  if(plan.targets.length<1 || plan.targets.length>40){Alert.alert('Target lines required','Add between 1 and 40 target lines.');return false}
  for(const t of plan.targets){if(!(t.customerIds?.length || t.customerId) || !t.from.trim() || t.fromLatitude==null || t.fromLongitude==null){Alert.alert('Incomplete target line','Each line needs customers and a selected From Location.');return false}}
  return true;
 };
 const next=()=>{if(step===1 && editIndex!==null){Alert.alert('Unsaved target','Save or cancel the target line before continuing.');return}if(step<3)setStep((step+1) as Step)};
 if(picker){const list=picker==='customers'?customers:employees;return <View style={{gap:10}}><View style={styles.row}><Text style={styles.title}>Select Odoo {picker==='customers'?'Customers':'Accompanying Employees'}</Text><Action title="Done" secondary onPress={()=>{setPicker(null);setQuery('')}}/></View><Control label="Search" value={query} onChange={setQuery} placeholder="Name, phone, or email"/>{loading&&<ActivityIndicator color={C.green}/ >}{!!loadError&&<Text style={styles.error}>{loadError}</Text>}<ScrollView nestedScrollEnabled keyboardShouldPersistTaps="always" style={{maxHeight:360}}>{list.map(item=>{const chosen=picker==='customers'?(target.customerIds||[]).includes(item.id):(target.employeeIds||[]).includes(item.id);return <Pressable key={item.id} style={[styles.listItem,chosen&&styles.selected]} onPress={()=>picker==='customers'?toggleCustomer(item as Customer):toggleEmployee(item as Employee)}><View style={{flex:1}}><Text style={styles.body}>{item.name}</Text></View><Text style={{color:chosen?C.green:C.muted,fontWeight:'800'}}>{chosen?'Selected':'Select'}</Text></Pressable>})}</ScrollView>{more&&<Action title="Load More" secondary disabled={loading} onPress={()=>void load(query,offset,picker)}/>}<Action title="Confirm Selection" onPress={()=>{setPicker(null);setQuery('')}}/></View>}
 return <View>
  <View style={styles.row}><Text style={styles.title}>Create Visit Plan</Text><Pressable onPress={onCancel}><Text style={{color:C.blue,fontWeight:'700'}}>Cancel</Text></Pressable></View>
  <View style={styles.steps}>{[{label:'Plan',icon:'◉'},{label:'Targets',icon:'⌖'},{label:'Expenses',icon:'৳'},{label:'Review',icon:'✓'}].map((item,i)=><Pressable key={item.label} style={[styles.step,step===i&&styles.stepActive]} onPress={()=>setStep(i as Step)}><Text style={[styles.stepLabel,step===i&&{color:'#FFFFFF'}]}>{item.icon} {item.label}</Text></Pressable>)}</View>
  {step===0&&<Panel><Text style={styles.section}>Basic Information</Text><Control label="Salesman (Odoo account)" value={salesperson||'Current logged-in salesperson'} onChange={()=>{}}/><Control label="Visit Date (YYYY-MM-DD)" value={plan.date} onChange={date=>onChange({date})}/><Text style={styles.label}>Purpose</Text><View style={styles.choices}>{PURPOSES.map(([value,label])=><Pressable key={value} onPress={()=>onChange({purpose:value})} style={[styles.chip,plan.purpose===value&&styles.chipSelected]}><Text style={[styles.chipText,plan.purpose===value&&{color:'#FFFFFF'}]}>{label}</Text></Pressable>)}</View><Text style={styles.label}>Priority</Text><View style={styles.choices}>{[['normal','Normal'],['high','High'],['urgent','Urgent']].map(([value,label])=><Pressable key={value} onPress={()=>onChange({priority:value})} style={[styles.chip,plan.priority===value&&styles.chipSelected]}><Text style={[styles.chipText,plan.priority===value&&{color:'#FFFFFF'}]}>{label}</Text></Pressable>)}</View><Caption>Total Visits (computed by Odoo): {plan.targets.reduce((n,t)=>n+(t.customerIds?.length|| (t.customerId?1:0)),0)}</Caption><Action title="Next: Target Lines" onPress={next}/></Panel>}
  {step===1&&<>
   <Panel>
    <Text style={styles.section}>{editIndex===null?'Add Target Line':`Edit Target Line ${editIndex+1}`}</Text>
    <Text style={styles.label}>Customers</Text>
    <Action title={(target.customerNames||[]).length?`Selected ${(target.customerNames||[]).length} Customer(s) — Change`:'Tap to Select Odoo Customers'} secondary onPress={()=>{setPicker('customers');setQuery('')}}/>
    <Caption>{(target.customerNames||[]).join(', ')||'No customers selected'}</Caption><Caption>Customer destination is detected automatically from the saved customer location.</Caption>
    <Text style={styles.label}>Accompanies</Text>
    <Action title={(target.employeeNames||[]).length?`Selected ${(target.employeeNames||[]).length} Employee(s) — Change`:'Select Accompanying Employees'} secondary onPress={()=>{setPicker('employees');setQuery('')}}/>
    <Caption>{(target.employeeNames||[]).join(', ')||'None'}</Caption>
    <Text style={styles.label}>From Location</Text>
    <View style={styles.locationActions}><Pressable style={[styles.currentLocationButton,capturingCurrentLocation&&{opacity:.55}]} disabled={capturingCurrentLocation} onPress={()=>void useCurrentLocation()}>{capturingCurrentLocation?<ActivityIndicator color="#FFFFFF"/>:<Text style={styles.currentLocationText}>⌖ Use My Current Location</Text>}</Pressable><Pressable style={styles.mapLocationButton} onPress={()=>{setCurrentLocationAccuracy(null);setLocationPicker(true)}}><Text style={styles.mapLocationText}>⌕ Search on Map</Text></Pressable></View>
    {target.from?<View style={styles.selectedLocation}><Text style={styles.selectedLocationText}>{target.from}</Text><Text style={styles.selectedLocationMeta}>{currentLocationAccuracy!=null?`GPS captured now · ± ${Math.round(currentLocationAccuracy)} m`:`${Number(target.fromLatitude).toFixed(6)}, ${Number(target.fromLongitude).toFixed(6)}`}</Text></View>:<Caption>Use your current GPS location or choose where the visit route starts on the map.</Caption>}
    <Control label="Expected KM" value={String(target.km??0)} onChange={v=>patchTarget({km:number(v)})} numeric/>
    {routeBusy&&<ActivityIndicator color={C.green}/ >}{!!routeError&&<Text style={styles.error}>{routeError}</Text>}
    {routePreview&&<View style={styles.routePreview}>
     <View style={styles.routePreviewHead}><View><Text style={styles.routePreviewTitle}>Road Route Preview</Text><Caption>Choose travel mode for route and ETA</Caption></View><View style={styles.routeBadge}><Text style={styles.routeBadgeText}>{routePreview.km.toFixed(2)} KM · {routePreview.minutes} min</Text></View></View>
     <View style={{flexDirection:'row',gap:7,paddingHorizontal:12,paddingBottom:10}}>{TRAVEL_MODES.map(mode=><Pressable key={mode.value} onPress={()=>setTravelMode(mode.value)} style={[{flex:1,minHeight:43,borderRadius:10,alignItems:'center',justifyContent:'center',backgroundColor:'#EAF7EE',borderWidth:1,borderColor:'#BDE1C4'},travelMode===mode.value&&{backgroundColor:C.blue,borderColor:C.blue}]}><Text style={{fontSize:14,marginBottom:1}}>{mode.icon}</Text><Text style={{fontSize:10,fontWeight:'800',color:travelMode===mode.value?'#FFFFFF':C.blue}}>{mode.label}</Text></Pressable>)}</View>
     <RoutePreviewMap route={routePreview} onInteractionChange={onMapInteractionChange}/>
     <Caption>Blue line shows the selected {routePreview.mode} route. ETA excludes live traffic.</Caption>
    </View>}
    <Action title={routeBusy?'Calculating distance…':'Recalculate Road KM'} secondary disabled={routeBusy||!target.from.trim()||!target.customerIds?.length} onPress={()=>void resolveKm()}/>
    <Control label="Target Notes" value={target.notes} onChange={v=>patchTarget({notes:v})}/><Action title={editIndex===null?'Add Target Line':'Save Target Changes'} onPress={saveTarget}/>
    {editIndex!==null&&<Action title="Cancel Editing Line" secondary onPress={()=>{setEditIndex(null);setRoutePreview(null);setCurrentLocationAccuracy(null);setTarget(newTarget())}}/>}
   </Panel>
   <Panel><Text style={styles.section}>Added Target Lines ({plan.targets.length})</Text>{!plan.targets.length&&<Caption>No target lines added yet.</Caption>}{plan.targets.map((t,i)=><View key={t.id} style={styles.targetCard}><Text style={styles.body}>{i+1}. {(t.customerNames||[t.customer]).join(', ')}</Text><Caption>From: {t.from} | {t.km||0} KM</Caption><View style={styles.row}><Action title="Edit" secondary onPress={()=>edit(i)}/><Action title="Remove" secondary onPress={()=>onChange({targets:plan.targets.filter((_,x)=>x!==i)})}/></View></View>)}<Action title="Next: Expenses & Notes" onPress={next}/></Panel>
  </>}
  {step===2&&<Panel><Text style={styles.section}>Expenses Claim</Text><Control label="Transport (BDT)" value={plan.transport?String(plan.transport):''} placeholder="Enter transport cost" numeric onChange={v=>onChange({transport:number(v)})}/><Control label="Food (BDT)" value={plan.food?String(plan.food):''} placeholder="Enter food cost" numeric onChange={v=>onChange({food:number(v)})}/><Control label="Other (BDT)" value={plan.other?String(plan.other):''} placeholder="Enter other cost" numeric onChange={v=>onChange({other:number(v)})}/><View style={styles.total}><Text style={styles.body}>Total Expenses</Text><Text style={styles.totalText}>{price(plan.transport+plan.food+plan.other)}</Text></View><Control label="Plan Notes" value={plan.notes} onChange={notes=>onChange({notes})} placeholder="Visit purpose and follow-up details"/><Action title="Next: Review & Submit" onPress={next}/></Panel>}
  {locationPicker&&<LocationPicker visible initial={{latitude:target.fromLatitude,longitude:target.fromLongitude,label:target.from}} onClose={()=>setLocationPicker(false)} onSelect={point=>{routeAttempt.current++;setRoutePreview(null);setCurrentLocationAccuracy(null);patchTarget({from:point.label,fromLatitude:point.latitude,fromLongitude:point.longitude,km:0});setLocationPicker(false)}}/>}{step===3&&<Panel><Text style={styles.section}>Submission Review</Text>{[['Salesman',salesperson||'Current account'],['Visit Date',plan.date],['Purpose',PURPOSES.find(p=>p[0]===plan.purpose)?.[1]||plan.purpose],['Priority',plan.priority],['Target Lines',String(plan.targets.length)],['Total Visits',String(plan.targets.reduce((n,t)=>n+(t.customerIds?.length|| (t.customerId?1:0)),0))],['Expenses',price(plan.transport+plan.food+plan.other)],['Status on submit','Submitted (approval required)']].map(([key,value])=><View key={key} style={styles.summaryRow}><Caption>{key}</Caption><Text style={styles.body}>{value}</Text></View>)}{plan.targets.map((t,i)=><View style={styles.targetCard} key={t.id}><Text style={styles.body}>Line {i+1}: {(t.customerNames||[t.customer]).join(', ')}</Text><Caption>{(t.employeeNames||[]).join(', ')||'No accompanies'}</Caption><Caption>From: {t.from} | KM {t.km||0}</Caption><Caption>{t.notes}</Caption></View>)}<Action title="Save Local Draft" secondary disabled={busy} onPress={()=>{if(valid())onSave()}}/><Action title="Submit to Odoo" disabled={busy} onPress={()=>{if(valid())onSubmit()}}/></Panel>}
 </View>;
}
const styles=StyleSheet.create({title:{fontSize:19,fontWeight:'800',color:C.text},section:{fontSize:16,fontWeight:'800',color:C.text,marginBottom:14},panel:{backgroundColor:'#FFFFFF',borderRadius:18,borderWidth:1,borderColor:C.line,padding:17,marginBottom:15},row:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:8,flexWrap:'wrap'},steps:{flexDirection:'row',flexWrap:'wrap',gap:5,marginVertical:16},step:{backgroundColor:'#E9F2F4',borderRadius:8,paddingVertical:10,paddingHorizontal:8},stepActive:{backgroundColor:C.blue},stepLabel:{fontSize:10,fontWeight:'700',color:C.blue},label:{fontSize:12,fontWeight:'800',color:'#456579',marginBottom:6},input:{backgroundColor:'#F9FCFA',color:C.text,fontSize:13,paddingVertical:12,paddingHorizontal:13,borderWidth:1,borderColor:'#DCE7E2',borderRadius:11},calculatedDistance:{backgroundColor:'#EDF8F0',borderWidth:1,borderColor:'#CDE7D2',borderRadius:11,paddingVertical:12,paddingHorizontal:13},calculatedDistanceText:{color:C.green,fontSize:13,fontWeight:'800'},caption:{color:C.muted,fontSize:11,lineHeight:17,marginBottom:9},body:{color:C.text,fontSize:13,fontWeight:'700',flexShrink:1},choices:{flexDirection:'row',flexWrap:'wrap',gap:7,marginBottom:16},chip:{backgroundColor:'#EAF7EE',paddingHorizontal:11,paddingVertical:9,borderRadius:9,flexGrow:1,alignItems:'center',justifyContent:'center',minHeight:42},chipSelected:{backgroundColor:C.blue},chipText:{color:C.blue,fontSize:11,fontWeight:'700',textAlign:'center'},action:{backgroundColor:C.blue,borderRadius:11,paddingVertical:13,paddingHorizontal:14,alignItems:'center',justifyContent:'center',marginVertical:5},secondary:{backgroundColor:'#EAF7EE',borderWidth:1,borderColor:'#BDE1C4'},actionText:{fontSize:12,fontWeight:'800',color:'#FFFFFF'},locationActions:{flexDirection:'row',gap:8,marginBottom:10},currentLocationButton:{flex:1,backgroundColor:C.blue,borderRadius:11,paddingVertical:13,paddingHorizontal:10,alignItems:'center',justifyContent:'center'},currentLocationText:{color:'#FFFFFF',fontSize:11,fontWeight:'800',textAlign:'center'},mapLocationButton:{flex:1,borderRadius:11,paddingVertical:13,paddingHorizontal:10,alignItems:'center',justifyContent:'center',backgroundColor:'#EAF7EE',borderWidth:1,borderColor:'#BDE1C4'},mapLocationText:{color:C.blue,fontSize:11,fontWeight:'800',textAlign:'center'},selectedLocation:{backgroundColor:'#F0FBF2',borderRadius:11,borderWidth:1,borderColor:'#CBE8D1',padding:11,marginBottom:12},selectedLocationText:{fontSize:12,fontWeight:'800',color:C.text,lineHeight:18},selectedLocationMeta:{fontSize:11,color:'#39844B',fontWeight:'700',marginTop:6},listItem:{padding:13,borderBottomWidth:1,borderBottomColor:C.line,flexDirection:'row',gap:10},selected:{backgroundColor:'#E7F7EB'},error:{color:'#BB3344',fontSize:12},routePreview:{marginBottom:12,borderWidth:1,borderColor:'#CFE4DB',borderRadius:14,overflow:'hidden',backgroundColor:'#F7FCF9'},routePreviewHead:{paddingHorizontal:12,paddingTop:12,flexDirection:'row',justifyContent:'space-between',gap:8,alignItems:'flex-start'},routePreviewTitle:{fontSize:13,fontWeight:'800',color:C.text,marginBottom:3},routeBadge:{backgroundColor:'#E4F7E8',borderRadius:9,paddingHorizontal:8,paddingVertical:6},routeBadgeText:{fontSize:10,fontWeight:'800',color:'#24853B'},targetCard:{borderWidth:1,borderColor:'#D5E7DB',backgroundColor:'#F8FCFA',borderRadius:12,padding:12,marginVertical:7},total:{backgroundColor:C.mint,padding:15,borderRadius:12,flexDirection:'row',justifyContent:'space-between',alignItems:'center'},totalText:{fontSize:16,fontWeight:'800',color:'#2D913D'},summaryRow:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',borderBottomWidth:1,borderBottomColor:C.line,paddingVertical:11,gap:15}});
