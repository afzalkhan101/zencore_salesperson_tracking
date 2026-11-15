import React,{useCallback,useEffect,useRef,useState} from 'react';
import {startAutoSync,triggerAutoSync,type AutoSyncSnapshot} from './src/services/autoSync';
import {Alert,ActivityIndicator,Animated,Easing,KeyboardAvoidingView,Modal,Platform,Pressable,ScrollView,StatusBar,StyleSheet,Text,TextInput,View,Image as RNImage,Linking} from 'react-native';
import {chooseAndQueuePhoto,deleteQueuedPhoto,getVisitPhotos,type VisitPhoto} from './src/services/photoEvidence';
import {photoPendingCount} from './src/services/storage';
import GradientBackground from './src/components/GradientBackground';
import NetInfo from '@react-native-community/netinfo';
import {C} from './src/theme/colors';
import type {Customer,Plan,Target} from './src/types/models';
import {initialize,getPlans,setPlans,gpsCount,getTrackingSession,getActivePlan,getActiveTracker,getPendingStopPlan,setPendingStopPlan,gpsSummary,getTrackingIdentity,getLastTrackingIdentity,trackingMetrics,localDistanceForPlans,type GpsSummary,type TrackingMetrics} from './src/services/storage';
import {flushPendingPlanStop} from './src/services/sync';
import * as Odoo from './src/services/odoo';
import * as GPS from './src/services/location';
import VisitPlanEditor from './src/components/VisitPlanEditor';
import LiveRouteMap from './src/components/LiveRouteMap';
import CustomerManager from './src/components/CustomerManager';

type Tab='Home'|'Visits'|'Tracking'|'Map'|'Profile';
const TODAY=()=>new Date().toISOString().slice(0,10);
const BUILD_TAG='ZENCORE_FIELD_V36_ODOO_PLANS_ONLY';
if (__DEV__) console.log('[ZenCore Build]',BUILD_TAG);
const createId=()=>`${Date.now()}-${Math.random().toString(36).slice(2)}`;
const planScope=(host:string,login:string)=>`v1_${host.trim().toLowerCase()}_${login.trim().toLowerCase()}`;
const purposes=[{key:'followup',label:'Follow Up'},{key:'order',label:'New Order'},{key:'payment',label:'Payment Collection'},{key:'complaint',label:'Complaint Resolution'},{key:'demo',label:'Product Demo'}];
const formatMoney=(n:number)=>`৳ ${Number(n||0).toFixed(2)}`;
const freshPlan=():Plan=>({localId:createId(),name:'New Visit Plan',date:TODAY(),purpose:'followup',priority:'normal',targets:[],transport:0,food:0,other:0,state:'draft',notes:''});
const safeNum=(s:string)=>Math.max(0,Number(s)||0);
const icons:Record<Tab,string>={Home:'⌂',Visits:'▣',Tracking:'⌖',Map:'▱',Profile:'♙'};
type DialogTone='success'|'warning'|'error'|'info';
type DialogAction={label:string;variant?:'primary'|'light'|'danger';onPress?:()=>void|Promise<void>};
type DialogState={title:string;message:string;tone:DialogTone;actions:DialogAction[]};
const evidencePanelStyle={backgroundColor:'#FCFFFD',borderColor:'#CBE9DD',borderWidth:1.5,borderRadius:24,padding:18,shadowColor:'#0B7A62',shadowOpacity:.10,shadowRadius:14,elevation:3};
const infoValueStyle={maxWidth:'58%',backgroundColor:'#F1F8F5',borderRadius:10,paddingHorizontal:9,paddingVertical:5};
const nextDistanceBadge={alignSelf:'flex-start' as const,backgroundColor:'#EAF4FB',borderRadius:12,paddingHorizontal:10,paddingVertical:6,marginTop:9};
const nextDistanceText={fontSize:11,fontWeight:'800' as const,color:'#07518C'};
function B({children,onPress,variant='primary',disabled=false}:{children:React.ReactNode;onPress:()=>void;variant?:'primary'|'light'|'danger'|'ghost';disabled?:boolean}){
 const label=typeof children==='string'?children:'';
 // Check-in is now created by the 100m server geofence. Keep the handler in
 // place for compatibility, but do not expose a manual button in the UI.
 if(label==='GPS Check In')return null;
 return <Pressable disabled={disabled} onPress={onPress} style={[st.btn,variant==='light'&&st.btnLight,variant==='danger'&&st.btnDanger,variant==='ghost'&&st.btnGhost,disabled&&{opacity:.5}]}><Text style={[st.btnLabel,variant!=='primary'&&{color:variant==='danger'?C.danger:C.blue}]}>{children}</Text></Pressable>
}
function Panel({children,style}:{children:React.ReactNode;style?:object}){
 const hasHeading=React.Children.toArray(children).some(child=>React.isValidElement(child)&&child.type===H);
 return <View style={[st.panel,hasHeading&&evidencePanelStyle,style]}>{children}</View>
}
function H({children}:{children:React.ReactNode}){return <Text style={st.heading}>{children}</Text>}
function Tiny({children}:{children:React.ReactNode}){return <Text style={st.muted}>{children}</Text>}
function Badge({children,tone='green'}:{children:React.ReactNode;tone?:'green'|'blue'|'amber'|'gray'}){return <View style={[st.badge,{backgroundColor:tone==='green'?'#E8F8DF':tone==='blue'?C.paleBlue:tone==='amber'?'#FFF1DB':'#EDF2F0'}]}><Text style={[st.badgeText,{color:tone==='green'?'#388F27':tone==='blue'?C.blue:tone==='amber'?C.amber:C.muted}]}>{children}</Text></View>}
function Field({label,value,onChange,placeholder,keyboardType}:{label:string;value:string;onChange:(v:string)=>void;placeholder?:string;keyboardType?:'numeric'|'default'|'phone-pad'}){return <View style={{marginBottom:12}}><Text style={st.fieldLabel}>{label}</Text><TextInput autoCapitalize="sentences" style={st.input} value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor="#A2B0B6" keyboardType={keyboardType||'default'}/></View>}
function Metric({icon,value,title}:{icon:string;value:string;title:string}){
 return <GradientBackground colors={['#FFFFFF','#F4FAFF','#E4F8ED']} start={{x:0,y:0}} end={{x:1,y:1}} style={[st.metric,st.metricGradient]}>
  <View style={st.metricSymbol}><Text style={st.metricIcon}>{icon}</Text></View>
  <Text style={st.metricNumber}>{value}</Text><Text style={st.metricCaption}>{title}</Text>
 </GradientBackground>;
}
function PageBanner({title,subtitle,code}:{title:string;subtitle:string;code:string}){
 return <GradientBackground colors={['#07518C','#06678E','#30B978','#79D747']} start={{x:0,y:0}} end={{x:1,y:1}} style={st.pageBanner}>
  <View style={st.pageBannerOrb}/>
  <Text style={st.pageBannerEyebrow}>ZENCORE FIELD  /  {code}</Text>
  <Text style={st.pageBannerTitle}>{title}</Text>
  <Text style={st.pageBannerSub}>{subtitle}</Text>
 </GradientBackground>;
}
function HealthCard({title,subtitle,tone}:{title:string;subtitle:string;tone:'green'|'blue'|'amber'}){
 const palette=tone==='green'?['#F3FFF5','#DAF9E0']:tone==='amber'?['#FFFDF4','#FFF1D3']:['#F5FBFF','#DEEFFB'];
 return <GradientBackground colors={[palette[0],palette[1]]} start={{x:0,y:0}} end={{x:1,y:1}} style={st.healthCard}>
  <View style={[st.healthDot,{backgroundColor:tone==='green'?'#70BF36':tone==='amber'?'#D59F3A':'#07518C'}]}/>
  <View style={{flex:1}}><Text style={st.healthTitle}>{title}</Text><Text style={st.healthSub}>{subtitle}</Text></View>
 </GradientBackground>;
}


const formatDuration=(milliseconds:number)=>{
 const s=Math.floor(Math.max(0,milliseconds)/1000);
 return `${String(Math.floor(s/3600)).padStart(2,'0')}:${String(Math.floor(s%3600/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;
};
// Tracking animation is visual only: the real status comes from SQLite/native GPS.
function TrackingPulse({active}:{active:boolean}){
 const progress=useRef(new Animated.Value(0)).current;
 useEffect(()=>{
  progress.stopAnimation();progress.setValue(0);
  if(!active)return;
  const loop=Animated.loop(Animated.timing(progress,{toValue:1,duration:1900,easing:Easing.out(Easing.ease),useNativeDriver:true}));
  loop.start();return()=>loop.stop();
 },[active,progress]);
 const scale=progress.interpolate({inputRange:[0,1],outputRange:[.75,1.65]});
 const opacity=progress.interpolate({inputRange:[0,1],outputRange:[.55,0]});
 return <View style={st.pulseRoot}>
  {active&&<Animated.View style={[st.pulseRing,{opacity,transform:[{scale}]}]}/>}
  <View style={[st.pulseCore,{backgroundColor:active?'#63CE4E':'#90AABD'}]}><Text style={st.pulseIcon}>{active?'●':'○'}</Text></View>
 </View>;
}
const displayDistance=(km:number|null)=>`${Number(km??0).toFixed(2)} km`;
const customerDistance=(m:TrackingMetrics,customers:Customer[])=>{
 if(m.latestLat==null||m.latestLng==null)return 'GPS pending';
 const dest=customers.find(c=>Number.isFinite(c.latitude)&&Number.isFinite(c.longitude));
 if(!dest||dest.latitude==null||dest.longitude==null||(dest.latitude===0&&dest.longitude===0))return 'Location unavailable';
 const rad=(v:number)=>v*Math.PI/180;
 const dlat=rad(dest.latitude-m.latestLat),dlng=rad(dest.longitude-m.latestLng);
 const a=Math.sin(dlat/2)**2+Math.cos(rad(m.latestLat))*Math.cos(rad(dest.latitude))*Math.sin(dlng/2)**2;
 const km=6371*2*Math.atan2(Math.sqrt(a),Math.sqrt(Math.max(0,1-a)));
 return `${km.toFixed(2)} km`;
};
const straightLineKm=(lat1:number,lng1:number,lat2:number,lng2:number)=>{
 const rad=(v:number)=>v*Math.PI/180;
 const dlat=rad(lat2-lat1),dlng=rad(lng2-lng1);
 const a=Math.sin(dlat/2)**2+Math.cos(rad(lat1))*Math.cos(rad(lat2))*Math.sin(dlng/2)**2;
 return 6371*2*Math.atan2(Math.sqrt(a),Math.sqrt(Math.max(0,1-a)));
};
// Odoo states are technical (for example, `in_progress`). Keep them in the
// API, but show the field team a clear status in the mobile UI.
const visitPlanStatus=(state:string,planId:number|undefined,tracking:boolean,activePlanId:number|null)=>{
 const normalized=String(state||'').toLowerCase();
 if(normalized==='completed')return {label:'Completed',tone:'green' as const,hint:'Open • Visit completed →'};
 if(normalized==='in_progress'){
  const recording=tracking&&activePlanId===planId;
  return {label:recording?'Tracking':'Not Tracking',tone:recording?'green' as const:'gray' as const,hint:recording?'Open • Tracking active →':'Open • Tracking available →'};
 }
 if(normalized==='approved')return {label:'Approved',tone:'green' as const,hint:'Open • Tracking available →'};
 if(normalized==='submitted')return {label:'Submitted',tone:'blue' as const,hint:'Open • Awaiting approval →'};
 if(normalized==='rejected')return {label:'Rejected',tone:'amber' as const,hint:'Open • Approval was rejected →'};
 if(normalized==='draft')return {label:'Draft',tone:'gray' as const,hint:'Open • Complete and submit →'};
 const label=normalized?normalized.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase()):'Not Started';
 return {label,tone:'gray' as const,hint:'Open plan →'};
};
export default function App(){
 const [tab,setTab]=useState<Tab>('Home');const [activePlanId,setActivePlanId]=useState<number|null>(null);const [plans,setLocalPlans]=useState<Plan[]>([]);const [planOwnerKey,setPlanOwnerKey]=useState('');const [serverPlans,setServerPlans]=useState<Odoo.RemotePlan[]>([]);
 const [editing,setEditing]=useState<Plan|null>(null);const [detail,setDetail]=useState<Plan|null>(null);const [serverDetail,setServerDetail]=useState<number|null>(null);
 const [customerList,setCustomerList]=useState<Customer[]>([]);const [search,setSearch]=useState('');const [customerPickerOpen,setCustomerPickerOpen]=useState(false);const [customersLoading,setCustomersLoading]=useState(false);const [customersMore,setCustomersMore]=useState(false);const [customersOffset,setCustomersOffset]=useState(0);const [target,setTarget]=useState<Target>({id:createId(),customer:'',from:'',to:'',notes:''});
 const [online,setOnline]=useState<boolean|null>(null);const [pending,setPending]=useState(0);const [tracking,setTracking]=useState(false);const [busy,setBusy]=useState(false);const [message,setMessage]=useState('');
 const [host,setHost]=useState('');const [database,setDatabase]=useState('');const [email,setEmail]=useState('');const [password,setPassword]=useState('');const [connected,setConnected]=useState(false);const [userName,setUserName]=useState('');
 const [authPage,setAuthPage]=useState<'login'|'register'|'forgot'>('login');
 const [regName,setRegName]=useState('');const [regPhone,setRegPhone]=useState('');
 const [regPassword,setRegPassword]=useState('');const [regConfirmPassword,setRegConfirmPassword]=useState('');
 const [trackerId,setTrackerId]=useState<number|null>(null);const [remoteDetailData,setRemoteDetailData]=useState<Odoo.RemotePlanDetail|null>(null);const [customerVisits,setCustomerVisits]=useState<Customer[]>([]);const [checkinIds,setCheckinIds]=useState<Record<number,number>>({});const [visitNotes,setVisitNotes]=useState('');
 const [photos,setPhotos]=useState<VisitPhoto[]>([]);const [pendingPhotos,setPendingPhotos]=useState(0);
 const [autoSync,setAutoSync]=useState<AutoSyncSnapshot>({phase:'waiting',pending:0,lastSuccessAt:null,lastError:null,nextAttemptAt:null});
 const [gpsStats,setGpsStats]=useState<GpsSummary>({total:0,pending:0,lastCapturedAt:null,lastAccuracy:null});
 const [queuedStop,setQueuedStop]=useState<number|null>(null);
 const [trackingNeedsRepair,setTrackingNeedsRepair]=useState(false);
 const [metrics,setMetrics]=useState<TrackingMetrics>({distanceMeters:0,durationMs:0,accuracyMeters:null,latestLat:null,latestLng:null,lastFixAt:null,acceptedFixes:0});
 const [now,setNow]=useState(Date.now());
 const [dialog,setDialog]=useState<DialogState|null>(null);
 const [profileCustomersOpen,setProfileCustomersOpen]=useState(false);
 const [profile,setProfile]=useState<Odoo.FieldProfile|null>(null);
 const [dashboard,setDashboard]=useState<Odoo.FieldDashboard|null>(null);
 const [localTotalKm,setLocalTotalKm]=useState(0);
 const [todaySummary,setTodaySummary]=useState<Odoo.FieldTodaySummary|null>(null);
 const [approvals,setApprovals]=useState<Odoo.ApprovalRequest[]>([]);
 const notify=(v:string)=>{
  setMessage('');
  const tone:DialogTone=/failed|error|denied|cannot|invalid|required|must |not found|locked|rejected|timeout/i.test(v)?'error':'success';
  setDialog({title:tone==='success'?'ZenCore Field':'Action needs attention',message:v,tone,actions:[{label:'Continue',variant:'primary'}]});
 };
 const refresh=useCallback(async()=>{try{
   setPending(await gpsCount());setPendingPhotos(await photoPendingCount());
   const device=await GPS.inspectTracking();
   setTracking(device.active);setActivePlanId(device.active?device.planId:null);
   setTrackerId(device.active?device.trackerId:null);
   setTrackingNeedsRepair(device.needsRecovery);
   setGpsStats(await gpsSummary(device.active?device.planId:null));
   const identity=device.active?await getTrackingIdentity():await getLastTrackingIdentity();
   setMetrics(await trackingMetrics(identity??null));
   setNow(Date.now());
   setQueuedStop(await getPendingStopPlan());
 }catch(e){setMessage(String(e))}},[]);
 useEffect(()=>{let mounted=true;initialize().then(async()=>{if(mounted)setLocalPlans([]);const h=await Odoo.getHost();const sessionOk=await Odoo.verifySession();if(mounted){setHost(h);setConnected(sessionOk);}if(sessionOk){
  const [p,d,t]=await Promise.allSettled([Odoo.fieldProfile(),Odoo.fieldDashboard(),Odoo.fieldTodaySummary()]);
  if(mounted){if(p.status==='fulfilled'){setProfile(p.value);setUserName(p.value.name);setEmail(p.value.login);const scope=planScope(h,p.value.login);setPlanOwnerKey(scope);setLocalPlans(await getPlans(scope));}if(d.status==='fulfilled')setDashboard(d.value);if(t.status==='fulfilled')setTodaySummary(t.value);}
 }await refresh()}).catch(e=>setMessage(String(e)));
 const sub=NetInfo.addEventListener(s=>setOnline(Boolean(s.isConnected&&s.isInternetReachable!==false)));
 const stopAuto=startAutoSync(snapshot=>{if(mounted){setAutoSync(snapshot);setPending(snapshot.pending)}});
 return()=>{mounted=false;sub();stopAuto()};},[refresh]);
 // Refresh Odoo approval/plan status automatically when the connection returns.
 // This read-only polling is independent of the GPS upload queue.
 useEffect(()=>{
   if(!online || !connected) return;
   let cancelled=false;
   const refreshPlans=async()=>{
     try {const [plansResult,profileResult,dashboardResult,todayResult]=await Promise.allSettled([
      Odoo.myVisitPlans(),Odoo.fieldProfile(),Odoo.fieldDashboard(),Odoo.fieldTodaySummary()]);
      if(cancelled)return;
      if(plansResult.status==='fulfilled')setServerPlans(plansResult.value.plans||[]);
      if(profileResult.status==='fulfilled'){setProfile(profileResult.value);setUserName(profileResult.value.name);}
      if(dashboardResult.status==='fulfilled')setDashboard(dashboardResult.value);
      if(todayResult.status==='fulfilled')setTodaySummary(todayResult.value);}
     catch(error){if(__DEV__)console.log('[ZenCore AutoSync] Plan refresh deferred:',error instanceof Error?error.message:String(error))}
   };
   void refreshPlans();
   const interval=setInterval(()=>{void refreshPlans()},60000);
   return()=>{cancelled=true;clearInterval(interval)};
 },[online,connected]);
 // Restore destination coordinates for a resumed active plan after app restart.
 useEffect(()=>{
  if(!connected || !online || !activePlanId)return;
  let cancelled=false;
  Odoo.getPlanDetail(activePlanId).then(({plan})=>{
    if(cancelled)return;
    const customers:Customer[]=[];
    for(const line of plan.targets||[]){
      (line.customer_ids||[]).forEach((id,index)=>{
        if(customers.some(c=>c.id===id))return;
        const geo=line.customer_locations?.find(c=>c.id===id);
        customers.push({id,name:line.customer_names?.[index]||`Customer #${id}`,
          latitude:geo?.latitude??undefined,longitude:geo?.longitude??undefined});
      });
    }
    setCustomerVisits(customers);
  }).catch(()=>{});
  return()=>{cancelled=true};
 },[connected,online,activePlanId]);
 useEffect(()=>{if(tab==='Visits'&&connected){Odoo.getPendingApprovals().then(v=>setApprovals(v.approvals)).catch(()=>{});}},[tab,connected]);
 useEffect(()=>{if(tab!=='Visits'||serverDetail===null)return;let alive=true;
  const poll=async()=>{
   try{
    const [items,customerResult]=await Promise.all([getVisitPhotos(serverDetail),Odoo.planCustomers(serverDetail)]);
    if(!alive)return;
    setPhotos(items);
    setCustomerVisits(customerResult.customers||[]);
    setCheckinIds(old=>{
     const next={...old};
     for(const customer of customerResult.customers||[]){
      if(customer.checkin_id)next[customer.id]=customer.checkin_id;
      else delete next[customer.id];
     }
     return next;
    });
    if(!tracking)setTrackerId(customerResult.tracker_id||null);
   }catch(_error){/* keep the last known visit state while offline */}
  };
  void poll();const timer=setInterval(()=>{void poll()},7000);return()=>{alive=false;clearInterval(timer)};
 },[tab,serverDetail,tracking]);
 useEffect(()=>{if(tab!=='Tracking' && tab!=='Map' && tab!=='Home')return;
  void refresh();const timer=setInterval(()=>{void refresh()},5000);return()=>clearInterval(timer);
 },[tab,refresh]);
 // V22 local GPS fallback; server plan IDs scope shared-device SQLite history.
 useEffect(()=>{
  if(!connected||!serverPlans.length){setLocalTotalKm(0);return;}
  let cancelled=false;
  const calculate=()=>localDistanceForPlans(serverPlans.map(p=>p.id)).then(km=>{if(!cancelled)setLocalTotalKm(km)}).catch(()=>{});
  void calculate();const timer=setInterval(()=>{void calculate()},15000);
  return()=>{cancelled=true;clearInterval(timer)};
 },[connected,serverPlans]);
 const save=async(p:Plan[])=>{setLocalPlans(p);await setPlans(p,planOwnerKey||'anonymous')};
 const updateEdit=(patch:Partial<Plan>)=>setEditing(old=>old?{...old,...patch}:old);
 const go=(t:Tab)=>{setTab(t);setEditing(null);setDetail(null);setServerDetail(null)};
 const run=async(action:()=>Promise<void>)=>{if(busy)return;setBusy(true);try{await action()}catch(e){notify(e instanceof Error?e.message:String(e))}finally{setBusy(false);await refresh()}};
 const fetchServer=()=>run(async()=>{
  const [result, pendingApprovals]=await Promise.all([Odoo.myVisitPlans(),Odoo.getPendingApprovals()]);
  setServerPlans(result.plans);setApprovals(pendingApprovals.approvals);
 });
 const refreshApprovals=()=>run(async()=>setApprovals((await Odoo.getPendingApprovals()).approvals));
 const decidePlan=(id:number,decision:'approve'|'reject')=>run(async()=>{
   await Odoo.decideApproval(id,decision);
   setApprovals((await Odoo.getPendingApprovals()).approvals);
   setServerPlans((await Odoo.myVisitPlans()).plans);
 });
 const login=()=>run(async()=>{const name=await Odoo.login(host,database,email,password);setPassword('');setConnected(true);setUserName(name);const scope=planScope(host,email);setPlanOwnerKey(scope);setLocalPlans(await getPlans(scope));triggerAutoSync(true);
  const [p,d,t]=await Promise.allSettled([Odoo.fieldProfile(),Odoo.fieldDashboard(),Odoo.fieldTodaySummary()]);
  if(p.status==='fulfilled'){setProfile(p.value);setUserName(p.value.name);setEmail(p.value.login);const scope=planScope(host,p.value.login);setPlanOwnerKey(scope);setLocalPlans(await getPlans(scope));}
  if(d.status==='fulfilled')setDashboard(d.value);if(t.status==='fulfilled')setTodaySummary(t.value);
  try{const result=await Odoo.myVisitPlans();setServerPlans(result.plans||[]);triggerAutoSync();notify('Connected to Odoo as '+name)}catch(e){notify('Odoo login succeeded, but loading Visit Plans failed: '+(e instanceof Error?e.message:String(e)))}});
 const addTarget=()=>{if(!editing)return;if(!target.customerId){notify('Tap the Customer field and select an Odoo customer from the list.');return}if(!target.from.trim()||!target.to.trim()){notify('Enter both From and To locations.');return}updateEdit({targets:[...editing.targets,target]});setTarget({id:createId(),customer:'',from:'',to:'',notes:''});setSearch('');setCustomerList([]);setCustomerPickerOpen(false)};
 // Load the first 50 readable contacts as soon as the picker opens. A request ID
 // protects against older search responses replacing a newer query.
 useEffect(()=>{
   if(!customerPickerOpen || !connected || !editing)return;
   const timer=setTimeout(()=>{
     setCustomersLoading(true);
     Odoo.findCustomers(search,0,50).then(page=>{
       if(!cancelled){setCustomerList(page.partners);setCustomersMore(page.has_more);setCustomersOffset(page.next_offset)}
     }).catch(e=>{if(!cancelled)setMessage(e instanceof Error?e.message:String(e))})
       .finally(()=>{if(!cancelled)setCustomersLoading(false)});
   },search?300:0);
   let cancelled=false;
   return()=>{cancelled=true;clearTimeout(timer)};
 },[search,customerPickerOpen,connected,editing?.localId]);
 const loadMoreCustomers=async()=>{
   if(customersLoading || !customersMore)return;
   setCustomersLoading(true);
   try{const page=await Odoo.findCustomers(search,customersOffset,50);
     setCustomerList(old=>[...old,...page.partners.filter(c=>!old.some(x=>x.id===c.id))]);
     setCustomersMore(page.has_more);setCustomersOffset(page.next_offset);
   }catch(e){notify(e instanceof Error?e.message:String(e))}
   finally{setCustomersLoading(false)}
 };
 const saveDraft=()=>run(async()=>{if(!editing)return;if(!editing.targets.length){notify('Add at least one target customer.');return}const p={...editing,state:'draft' as const,name:editing.name==='New Visit Plan'?`Draft ${editing.date}`:editing.name};await save([p,...plans.filter(x=>x.localId!==p.localId)]);setEditing(null);setDetail(p);notify('Draft saved on this device. Not submitted to Odoo.')});
 const submit= (p:Plan)=>run(async()=>{if(!online)throw Error('Internet required to submit. Your local draft is preserved.');if(!connected)throw Error('Connect to Odoo first.');const answer=await Odoo.submitPlan(p,true);const updated:Plan={...p,serverId:answer.plan_id,name:answer.plan_name,state:answer.state as Plan['state']};await save([updated,...plans.filter(x=>x.localId!==p.localId)]);setEditing(null);setDetail(updated);const latest=await Odoo.myVisitPlans();setServerPlans(latest.plans);notify(answer.state==='approved'?'Plan approved automatically. Tracking is available on the visit date.':'Plan submitted to the assigned approver. Tracking remains locked until approval.')});
 // Switching is deliberately explicit: ask before stopping a different active plan.
 // Server-side switch is transactional, but changing the phone's native GPS task
 // is not part of that database transaction. Compensating recovery is provided.
 const performPlanStart=(planId:number)=>run(async()=>{
   const prior=await GPS.inspectTracking();
   if(prior.needsRecovery)throw Error('Device tracking state requires repair. Open Tracking and tap Repair Tracking State.');
   if(await getPendingStopPlan()){
     if(!online || !connected)throw Error('Internet and Odoo login required to confirm the previous stop.');
     await flushPendingPlanStop();
     if(await getPendingStopPlan())throw Error('Previous tracking stop is still pending Odoo confirmation.');
   }
   if(!online || !connected)throw Error('An internet connection and Odoo login are required to switch plans. Existing tracking is not changed.');
   if(prior.active && prior.planId===planId){setTab('Tracking');return;}
   const oldPlanId=prior.active?prior.planId:null;
   const oldTrackerId=prior.active?prior.trackerId:null;
   const isSwitch=Boolean(oldPlanId && oldPlanId!==planId);
   // Stop local capture first: every point already stored retains its ORIGINAL plan/tracker.
   if(isSwitch)await GPS.stopTracking();
   let remoteStarted=false;
   let newTrackerId:number|null=null;
   try {
     const result=await Odoo.switchPlanTracking(planId);
     if(!result.ok || !result.is_tracking || !Number.isInteger(result.tracker_id) || result.tracker_id<=0)
       throw Error('Odoo did not confirm activation of the selected tracker.');
     remoteStarted=true;
     newTrackerId=result.tracker_id;
     // If an identical device session was already running, avoid a duplicate task.
     await GPS.startTracking(result.tracker_id,planId);
   }catch(error){
     const reasons=[error instanceof Error?error.message:String(error)];
     if(remoteStarted){
       try{await Odoo.stopPlanTracking(planId)}catch(e){reasons.push('New Odoo tracker may remain active; check Odoo before retrying.')}
     }
     if(isSwitch && oldPlanId && oldTrackerId){
       try {
         // Restore both remote and local prior tracking whenever possible.
         const restored=await Odoo.startPlanTracking(oldPlanId);
         if(!restored.ok || !restored.is_tracking || restored.tracker_id!==oldTrackerId)
           throw Error('Previous tracker identity changed');
         await GPS.startTracking(oldTrackerId,oldPlanId);
         reasons.push('Previous tracking restored.');
       }catch(recoveryError){
         reasons.push('Automatic recovery failed. Review Tracking screen and Odoo tracker state before starting again.');
       }
     }
     throw Error(reasons.join(' '));
   }
   setTrackerId(newTrackerId);setActivePlanId(planId);setTracking(true);
   setTab('Tracking');setTrackingNeedsRepair(false);
   triggerAutoSync(true);
   try{setServerPlans((await Odoo.myVisitPlans()).plans)}catch(_error){}
   notify(isSwitch?`Previous tracking stopped. Plan #${planId} is now recording.`:`GPS recording started for Plan #${planId}.`);
 });
 const startApprovedPlan=async(planId:number)=>{
  // One tap: server-side switch stops ALL other owned active trackers.
  // No confirmation dialog; failed server activation never shows false local success.
  if(busy)return;
  void performPlanStart(planId);
 };
 const stopActivePlan=()=>run(async()=>{
   const device=await GPS.inspectTracking();
   if(!device.active){
     if(device.needsRecovery)throw Error('Tracking state requires repair. Use Repair Tracking State below.');
     notify('Tracking is already stopped on this device.');return;
   }
   const planId=device.planId!;
   // Persist intent before stopping native capture. Retain it across crashes/offline.
   await setPendingStopPlan(planId);
   await GPS.stopTracking();
   setTracking(false);setActivePlanId(null);setTrackerId(null);
   let confirmed=false;
   if(online && connected){
     try{confirmed=await flushPendingPlanStop();}
     catch(e){console.warn('[ZenCore V16] Stop queued for retry',e);}
   }
   triggerAutoSync(true);
   notify(confirmed
     ? `Tracking stopped for Plan #${planId}. You can start it again or choose another Approved Plan. GPS uploads continue separately.`
     : `GPS stopped for Plan #${planId}. Odoo stop is pending; it will retry automatically online. GPS data is preserved.`);
 });
 const repairDeviceTracking=()=>run(async()=>{
   const prior=await GPS.repairTracking();
   if(prior.planId){
     if(!(await getPendingStopPlan()))await setPendingStopPlan(prior.planId);
     triggerAutoSync(true);
   }
   setTracking(false);setActivePlanId(null);setTrackerId(null);setTrackingNeedsRepair(false);
   notify(prior.planId
     ? `Recovered inconsistent GPS state for Plan #${prior.planId}. Server stop will be retried after GPS uploads. Review this plan in Odoo.`
     : 'Orphaned GPS capture stopped safely. No Plan ID was available; check Odoo for any remotely active tracker.');
 });
 const confirmStopActivePlan=()=>{
   setDialog({title:'Stop Plan Tracking',message:'Stop GPS capture for this Visit Plan? Unsynced points will remain queued and upload automatically when online.',tone:'warning',actions:[
     {label:'Cancel',variant:'light'},
     {label:'Stop Tracking',variant:'danger',onPress:stopActivePlan},
   ]});
 };
 const toggleTracking=()=>{
   if(tracking){confirmStopActivePlan();return;}
   if(trackingNeedsRepair){repairDeviceTracking();return;}
   // When tracking is stopped, take the salesperson directly to the Visit
   // Plans list. They can open an approved plan and start tracking from its
   // detail view; no informational warning is needed here.
   go('Visits');
 };
 const openServerPlan=(id:number)=>run(async()=>{
   const detailed=await Odoo.getPlanDetail(id);
   setRemoteDetailData(detailed.plan);
   // Load plan-scoped customer status so automatic server geofence events are
   // reflected in the mobile UI (including an active check-in ID).
   const customerResult=await Odoo.planCustomers(id);
   setCustomerVisits(customerResult.customers||[]);
   setCheckinIds(Object.fromEntries((customerResult.customers||[]).filter(c=>c.checkin_id).map(c=>[c.id,c.checkin_id as number])));
   if(!tracking)setTrackerId(customerResult.tracker_id||detailed.plan.tracker_id||null);
   setServerDetail(id);setPhotos(await getVisitPhotos(id));
 });
 const choosePhoto=(camera:boolean)=>run(async()=>{
   if(serverDetail===null)throw Error('Open an Odoo Visit Plan to attach evidence.');
   const item=await chooseAndQueuePhoto(serverDetail,trackerId,null,visitNotes,camera);
   if(item){setPhotos(await getVisitPhotos(serverDetail));setPendingPhotos(await photoPendingCount());triggerAutoSync(true);notify('Photo saved on this device. It will upload to Odoo Chatter automatically when online.');}
 });
 const removePhoto=(photo:VisitPhoto)=>run(async()=>{await deleteQueuedPhoto(photo);if(serverDetail!==null)setPhotos(await getVisitPhotos(serverDetail));setPendingPhotos(await photoPendingCount());});
 const checkCustomer=(cust:Customer)=>run(async()=>{
   if(cust.visited)throw Error('This customer visit is already completed.');
   if(!tracking || !activePlanId || activePlanId!==serverDetail)throw Error('Start tracking this exact Approved Plan before customer check-in/out.');
   if(!trackerId)throw Error('No tracker assigned to this plan.');
   const coords=await GPS.currentGps();
   const activeCheckinId=checkinIds[cust.id]||cust.checkin_id||null;
   if(activeCheckinId){
     await Odoo.checkOut(activeCheckinId,{latitude:coords.coords.latitude,longitude:coords.coords.longitude,notes:visitNotes,outcome:'completed'});
     setCheckinIds(old=>{const n={...old};delete n[cust.id];return n});
     notify('Customer checked out in Odoo.');
   }else{
     const a=await Odoo.checkIn({partner_id:cust.id,tracker_id:trackerId,latitude:coords.coords.latitude,longitude:coords.coords.longitude});
     setCheckinIds(old=>({...old,[cust.id]:a.checkin_id}));
     notify('Customer checked in to Odoo.');
   }
 });
 const currencyTotal=editing?editing.transport+editing.food+editing.other:0;
 const nextVisitDistance=todaySummary?.next_visit&&metrics.latestLat!=null&&metrics.latestLng!=null&&todaySummary.next_visit.latitude!=null&&todaySummary.next_visit.longitude!=null
  ? `${straightLineKm(metrics.latestLat,metrics.latestLng,todaySummary.next_visit.latitude,todaySummary.next_visit.longitude).toFixed(2)} km away`
  : 'Distance unavailable';
 return <View style={st.root}><StatusBar barStyle="dark-content"/>
 <View style={st.header}><View><Text style={st.brand}>zen<Text style={{color:C.green}}>core</Text> <Text style={{fontSize:13,color:C.green}}>FIELD</Text></Text><Text style={st.headerSubtitle}>Field Sales Workspace</Text></View><View style={st.avatar}><Text style={{fontWeight:'800',color:C.blue}}>ZF</Text></View></View>
 <KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS==='ios'?'padding':undefined}><ScrollView contentContainerStyle={st.scroll} keyboardShouldPersistTaps="handled"><GradientBackground pointerEvents="none" colors={["#F3FBF7","#EDF9F5","#E9F6FE","#F4FBF8"]} start={{x:0,y:0}} end={{x:1,y:1}} style={st.ambient}/>
 {tab==='Home'&&<>
 <Text style={st.eyebrow}>WELCOME TO ZENCORE FIELD</Text>
 <H>Today's Overview</H>
 <GradientBackground colors={['#063E78','#086B87','#12A077','#62CF49']} start={{x:0,y:0}} end={{x:1,y:1}} style={st.hero}>
  <View style={st.heroOrb}/><View style={st.heroOrbSmall}/>
  <View style={st.heroHeaderRow}>
   <View style={{flex:1}}><Text style={st.heroKicker}>ZENCORE FIELD  /  LIVE STATUS</Text>
    <View style={st.heroPill}><View style={[st.heroPillDot,{backgroundColor:tracking?'#81F05A':'#C9D9E1'}]}/><Text style={st.heroPillLabel}>{tracking?'TRACKING ACTIVE':'TRACKING INACTIVE'}</Text></View>
   </View>
   <TrackingPulse active={tracking}/>
  </View>
  <Text style={st.heroTitle}>{tracking?'Your work route is being recorded':'Ready for your next visit'}</Text>
  <Text style={st.heroSub}>{tracking&&activePlanId?`Visit Plan #${activePlanId} · GPS tracking active`:'Start tracking from an approved visit plan'}</Text>
  <Pressable onPress={()=>go('Tracking')} accessibilityRole="button" accessibilityLabel="Open tracking" style={st.heroButton}><Text style={st.heroButtonText}>Open Tracking</Text><Text style={st.heroButtonArrow}>›</Text></Pressable>
 </GradientBackground>
 <View style={st.metrics}>
  <Metric icon="▣" value={connected?String(dashboard?.visit_plans??serverPlans.length):'0'} title="Overall Visit Plans"/>
  <Metric icon="✓" value={connected?String(dashboard?.completed_visits??dashboard?.completed_customer_visits??0):'0'} title="Overall Completed Visits"/>
  <Metric icon="♙" value={String(dashboard?.completed_customer_visits??0)} title="Overall Customers Visited"/>
  <Metric icon="⌁" value={displayDistance(Math.max(dashboard?.total_distance_km??0,localTotalKm))} title="Total Distance Traveled"/>
 </View>
 <Panel style={st.dailyCard}>
  <View style={st.topLine}><Text style={st.cardTitle}>Today's Visit Progress</Text><Badge tone="green">{todaySummary?`${todaySummary.completed_targets} / ${todaySummary.total_targets}`:'—'}</Badge></View>
  <View style={st.progressTrack}><View style={[st.progressFill,{width:`${todaySummary&&todaySummary.total_targets>0?Math.min(100,Math.round(todaySummary.completed_targets*100/todaySummary.total_targets)):0}%`}]}/></View>
  <Text style={st.progressDescription}>{todaySummary?`${todaySummary.completed_targets} completed · ${Math.max(0,todaySummary.total_targets-todaySummary.completed_targets)} remaining`:'Today’s schedule unavailable'}</Text>
 </Panel>
 <Panel style={st.dailyCard}>
  <View style={st.topLine}><Text style={st.cardTitle}>Next Customer Visit</Text><Badge tone={todaySummary?.next_visit?'blue':'gray'}>{todaySummary?.next_visit?'Upcoming':'No target'}</Badge></View>
  {todaySummary?.next_visit? <>
   <Text style={st.nextCustomerName}>{todaySummary.next_visit.customer_name}</Text>
   <View style={nextDistanceBadge}><Text style={nextDistanceText}>⌖ {nextVisitDistance}</Text></View>
   <Text style={st.nextCustomerAddress}>{todaySummary.next_visit.location||'Address not available'}</Text>
   <Text style={st.nextCustomerPlan}>{todaySummary.next_visit.plan_name}</Text>
   <Pressable style={st.dailyAction} onPress={()=>{go('Visits');void openServerPlan(todaySummary.next_visit!.plan_id)}} accessibilityRole="button"><Text style={st.dailyActionLabel}>View Visit Details</Text><Text style={st.dailyActionLabel}>›</Text></Pressable>
  </>:<Text style={st.muted}>No remaining customer visit in today's available plans.</Text>}
 </Panel>
 <Panel style={st.dailyCard}>
  <View style={st.topLine}><Text style={st.cardTitle}>Today's Visit Schedule</Text><Text style={st.dailyCount}>{todaySummary?.schedule.length??0} targets</Text></View>
  {(todaySummary?.schedule||[]).length?todaySummary!.schedule.slice(0,5).map(item=><Pressable key={item.line_id} onPress={()=>{go('Visits');void openServerPlan(item.plan_id)}} style={st.scheduleRow} accessibilityRole="button">
   <View style={[st.scheduleDot,{backgroundColor:item.visited?'#70BF36':'#07518C'}]}/>
   <View style={{flex:1}}><Text style={st.scheduleTitle} numberOfLines={1}>{item.customer_names.join(', ')||'Target visit'}</Text><Text style={st.muted} numberOfLines={1}>{item.plan_name}</Text></View>
   <Badge tone={item.visited?'green':'blue'}>{item.visited?'Completed':'Upcoming'}</Badge>
  </Pressable>):<Text style={st.muted}>No scheduled visits found for today.</Text>}
 </Panel>
 <View style={st.dailyNetworkRow}><View style={[st.networkDot,{backgroundColor:online?'#70BF36':'#95A8B4'}]}/><Text style={st.networkText}>{online?'Online':'Offline'} · GPS data syncs automatically</Text></View>
 </>}
 {tab==='Visits'&&<><PageBanner code="VISITS" title="Visit Plans" subtitle="Plan, submit and manage customer visits"/>{editing?<VisitPlanEditor plan={editing} salesperson={userName} onChange={updateEdit} onSave={saveDraft} onSubmit={()=>submit(editing)} onCancel={()=>setEditing(null)} busy={busy}/>:detail?<><B variant="ghost" onPress={()=>setDetail(null)}>‹ Back to Plans</B><H>{detail.name}</H><Panel><Info label="Status" value={detail.state}/><Info label="Date" value={detail.date}/><Info label="Purpose" value={detail.purpose}/><Info label="Targets" value={String(detail.targets.length)}/><Info label="Expense Total" value={formatMoney(detail.transport+detail.food+detail.other)}/>{detail.targets.map(x=><View style={st.targetRow} key={x.id}><View><Text style={st.body}>{x.customer}</Text><Tiny>{x.from} → {x.to}</Tiny></View></View>)}{detail.state==='draft'&&<B onPress={()=>submit(detail)}>Submit for Approval</B>}</Panel></>:serverDetail!==null?<><B variant="ghost" onPress={()=>setServerDetail(null)}>‹ Back to Plans</B><H>{serverPlans.find(p=>p.id===serverDetail)?.name || `Odoo Visit #${serverDetail}`}</H>
 <Panel><Info label="Salesperson" value={serverPlans.find(p=>p.id===serverDetail)?.salesperson||'—'}/><Info label="Plan ID" value={String(serverDetail)}/><Info label="Plan Status" value={visitPlanStatus(serverPlans.find(p=>p.id===serverDetail)?.state||'',serverDetail,tracking,activePlanId).label}/><Info label="Tracker ID" value={String(serverPlans.find(p=>p.id===serverDetail)?.tracker_id||'Not started')}/>{remoteDetailData&&<><Info label="Priority" value={remoteDetailData.priority}/><Info label="Expenses Total" value={formatMoney(remoteDetailData.total_cost)}/><Info label="Target Lines" value={String(remoteDetailData.targets.length)}/>{remoteDetailData.targets.map((line,i)=><View key={line.id} style={st.targetRow}><View style={{flex:1}}><Text style={st.body}>Line {i+1}: {line.customer_names.join(', ')}</Text><Tiny>{line.employee_names.join(', ')||'No accompanies'}</Tiny><Tiny>{line.from_location} to {line.to_location} | {line.expected_km} KM</Tiny><Tiny>{line.notes}</Tiny></View></View>)}</>}
 {(['approved','in_progress'].includes(serverPlans.find(p=>p.id===serverDetail)?.state||''))&& activePlanId!==serverDetail && <B disabled={busy} onPress={()=>{void startApprovedPlan(serverDetail)}}>{tracking?'Switch Tracking to This Plan':'Start Tracking for This Plan'}</B>}
 {tracking && activePlanId===serverDetail && <B variant="danger" onPress={confirmStopActivePlan}> Stop This Plan</B>}
 {!['approved','in_progress'].includes(serverPlans.find(p=>p.id===serverDetail)?.state||'') && <Tiny>Tracking locked until approval by your assigned superior.</Tiny>}</Panel>
 {customerVisits.length===0?<Panel><Tiny>No customers found for this plan.</Tiny></Panel>:customerVisits.map(c=><Panel key={c.id}><Text style={st.cardTitle}>{c.name}</Text><Tiny>{[c.street,c.city].filter(Boolean).join(', ')}</Tiny><Info label="Phone" value={c.phone||'—'}/><Info label="Visit" value={c.visited?'Visited':'Not visited'}/><B onPress={()=>checkCustomer(c)} variant={checkinIds[c.id]?'danger':'primary'}>{checkinIds[c.id]?'Check Out':'GPS Check In'}</B></Panel>)}<Panel><H>Visit Photos & Chatter Evidence</H><Field label="Visit Notes (saved with new photos)" value={visitNotes} onChange={setVisitNotes}/><View style={st.actions}><B onPress={()=>choosePhoto(true)}>Take Photo</B><B variant="light" onPress={()=>choosePhoto(false)}>Gallery</B></View><B variant="ghost" onPress={()=>run(async()=>{if(serverDetail!==null){triggerAutoSync(true);setPhotos(await getVisitPhotos(serverDetail));}})}>Refresh Photo Status</B>{photos.length===0?<Tiny>No photos selected yet.</Tiny>:photos.map(p=><View key={p.id} style={{marginTop:10}}><RNImage source={{uri:p.fileUri}} style={{height:170,width:"100%",borderRadius:12}} resizeMode="cover"/><Text style={st.body}>{p.fileName}</Text><Badge tone={p.status==='uploaded'?'green':'amber'}>{p.status==='uploaded'?`Uploaded to Odoo Chatter #${p.messageId}`:'Pending upload'}</Badge>{Boolean(p.error)&&<Tiny>{p.error}</Tiny>}{p.status==='pending'&&<B variant="ghost" onPress={()=>removePhoto(p)}>Remove Pending Photo</B>}</View>)}</Panel></>:<>
 <View style={st.topLine}><H>My Visit Plans</H><B onPress={()=>{setEditing(freshPlan());setTarget({id:createId(),customer:'',from:'',to:'',notes:''})}}>+ New Plan</B></View>
 <Panel><View style={st.topLine}><Text style={st.cardTitle}>Odoo Plans</Text><Badge tone={connected?'green':'amber'}>{connected?'Connected':'Demo / Offline'}</Badge></View><B variant="light" onPress={fetchServer}>↻ Refresh Odoo Plans</B></Panel>
 {connected&&<Panel><View style={st.topLine}><Text style={st.cardTitle}>My Team Approvals ({approvals.length})</Text><B variant="light" onPress={refreshApprovals}>Refresh</B></View>{approvals.length===0?<Tiny>No pending team approvals.</Tiny>:approvals.map(req=><View key={req.id} style={{paddingVertical:10,borderBottomWidth:1,borderBottomColor:C.line}}><Text style={st.cardTitle}>{req.name}</Text><Tiny>{req.owner} · {req.role} · {req.visit_date}</Tiny><Tiny>{req.customer_names}</Tiny><View style={st.actions}><B onPress={()=>decidePlan(req.id,'approve')}>Approve</B><B variant="danger" onPress={()=>decidePlan(req.id,'reject')}>Reject</B></View></View>)}</Panel>}
 {serverPlans.map(p=>{const status=visitPlanStatus(p.state,p.id,tracking,activePlanId);return <Pressable key={p.id} onPress={()=>openServerPlan(p.id)}><Panel><View style={st.topLine}><Text style={st.cardTitle}>{p.name}</Text><Badge tone={status.tone}>{status.label}</Badge></View><Tiny>{p.visit_date} · {p.total_visits} target visits</Tiny><Text style={st.linkText}>{status.hint}</Text></Panel></Pressable>})}
 </>}</>}
 {tab==='Tracking'&&<><PageBanner code="TRACKING" title="Live Tracking" subtitle="Plan-specific GPS recording and automatic Odoo sync"/>
  <View style={st.topLine}><H>Live Tracking</H><Badge tone={tracking?'green':'gray'}>{tracking?'ACTIVE':'STOPPED'}</Badge></View>
  <GradientBackground colors={['#F3FFF5','#DAF9E0']} style={st.trackingSummary}>
   <View style={st.topLine}><Text style={st.cardTitle}>{tracking?'Tracking in Progress':'Tracking Paused / Stopped'}</Text><Badge tone={tracking?'green':'gray'}>{tracking?'RECORDING':'STOPPED'}</Badge></View>
   <Text style={[st.body,{marginVertical:9}]}>{activePlanId?`Visit Plan #${activePlanId}`:'No active Visit Plan'}</Text>
   <View style={st.metricRow}>
    <View style={st.liveMetric}><Text style={st.liveValue}>{(metrics.distanceMeters/1000).toFixed(2)} km</Text><Tiny>Distance Traveled (GPS)</Tiny></View>
    <View style={st.liveMetric}><Text style={st.liveValue}>{metrics.accuracyMeters==null?'—':`± ${Math.round(metrics.accuracyMeters)} m`}</Text><Tiny>Latest Accuracy</Tiny></View>
   </View>
   <View style={st.metricRow}>
    <View style={st.liveMetric}><Text style={st.liveValue}>{tracking?formatDuration(metrics.durationMs):'—'}</Text><Tiny>Tracking Duration</Tiny></View>
    <View style={st.liveMetric}><Text style={st.liveValue}>{customerDistance(metrics,customerVisits)}</Text><Tiny>Next Customer (straight line)</Tiny></View>
   </View>
   <Info label="Last GPS fix" value={metrics.lastFixAt?new Date(metrics.lastFixAt).toLocaleString():'Waiting for GPS'}/>
  </GradientBackground>
  <Panel><Info label="Network" value={online?'Online':'Offline'}/><Info label="Odoo GPS upload" value={autoSync.phase==='up-to-date'?'Up to date':autoSync.phase.replace(/-/g,' ')}/>
    <Info label="Active Plan ID" value={activePlanId?`#${activePlanId}`:'None selected'}/>
    <Info label="Odoo Tracker" value={trackerId?`#${trackerId}`:'Not loaded'}/>
    <Info label="Device State" value={trackingNeedsRepair?'REPAIR REQUIRED':tracking?'Healthy / Recording':'Stopped'}/>
    <Info label="Stop acknowledgement" value={queuedStop?`Pending Plan #${queuedStop}`:'No pending stop'}/>
    <B onPress={toggleTracking} variant={tracking?'danger':'primary'}>{tracking?'Stop Tracking':trackingNeedsRepair?'Repair Tracking State':'Select Approved Plan in Visits'}</B>
    
    
  </Panel></>}
 {tab==='Map'&&<><PageBanner code="MAP" title="Live Map" subtitle=""/>
  <LiveRouteMap active={tracking} online={online} label={userName||'You'} destination={tracking?(()=>{const c=customerVisits.find(x=>Number.isFinite(x.latitude)&&Number.isFinite(x.longitude)&&x.latitude!==0&&x.longitude!==0);return c?.latitude!=null&&c.longitude!=null?{latitude:c.latitude,longitude:c.longitude}:null})():null}/>
  <Panel style={{marginTop:14}}><Text style={st.cardTitle}>Visit Route</Text>
   <Info label="Active Visit Plan" value={activePlanId?`#${activePlanId}`:'Not started'}/>
   <Info label="Tracking" value={tracking?'Recording':'Stopped'}/>
   
   {!tracking&&<B onPress={()=>go('Visits')}>Select Approved Plan in Visits</B>}
  </Panel></>}
 {tab==='Profile'&&<><PageBanner code="PROFILE" title={connected?'My Profile':'Connect to Odoo'} subtitle={connected?'Account and role information':'Secure Odoo login'}/>
  {connected?<>
   <Panel><View style={st.profileHeader}>
    <View style={st.profileAvatar}><Text style={st.profileAvatarText}>{(profile?.name||userName||'ZF').trim().split(/\s+/).slice(0,2).map(x=>x[0]||'').join('').toUpperCase()}</Text></View>
    <View style={{flex:1}}><Text style={st.profileName}>{profile?.name||userName||'Odoo User'}</Text><Badge tone="green">{profile?.role||'User'}</Badge></View>
   </View>
   <Info label="Odoo Connection" value={online?'Connected':'Offline (saved session)'}/>
   <Info label="Company" value={profile?.company||'Not available'}/>
   <Info label="Login / Email" value={profile?.login||'Not available'}/>
   <Info label="Role" value={profile?.role||'Not available'}/>
   <Info label="Reports To" value={profile?.reports_to||'Not assigned'}/>
   <Info label="App Version" value="v1"/>
   <B variant="light" onPress={()=>setProfileCustomersOpen(v=>!v)}>{profileCustomersOpen?'Close Customers':'Customers / Add Customer'}</B>
   <B variant="danger" onPress={()=>{
      const perform=()=>run(async()=>{await Odoo.logout();setConnected(false);setProfile(null);setDashboard(null);setUserName('');setServerPlans([]);setPlanOwnerKey('');setLocalPlans([]);setEmail('');setPassword('');notify('Signed out. Local unsynced records have not been deleted.');});
      if(tracking||pending>0||pendingPhotos>0){Alert.alert('Sign out?', 'Tracking or unsynced data may need Odoo access. Local records will be preserved, but auto-upload pauses until you sign in again.',[{text:'Cancel',style:'cancel'},{text:'Sign Out',style:'destructive',onPress:perform}]);}
      else perform();
   }}>Sign Out</B>
   </Panel>
   {profileCustomersOpen&&<CustomerManager onClose={()=>setProfileCustomersOpen(false)} onSaved={()=>{setCustomerList([]);setCustomersOffset(0);setCustomersMore(false);}}/>}
  </>:<>
   {authPage==='login'?<Panel>
    <Text style={st.cardTitle}>Connect to Odoo</Text>
    <Field label="Odoo URL" value={host} onChange={setHost} placeholder="https://your-odoo.example.com"/>
    <Field label="Database" value={database} onChange={setDatabase} placeholder="odoo_database"/>
    <Field label="Login / Email" value={email} onChange={setEmail} placeholder="user@example.com"/>
    <View style={{marginBottom:12}}><Text style={st.fieldLabel}>Password</Text><TextInput value={password} secureTextEntry onChangeText={setPassword} style={st.input} placeholder="Password" placeholderTextColor="#A2B0B6"/></View>
    <B onPress={login}>Sign In to Odoo</B>
    <B variant="ghost" onPress={()=>{setPassword('');setAuthPage('register')}}>Create New Account</B>
    <B variant="ghost" onPress={()=>{setPassword('');setAuthPage('forgot')}}>Forgot Password?</B>
   </Panel>:authPage==='register'?<Panel>
    <Text style={st.cardTitle}>Create Salesperson Account</Text>
    <Text style={st.help}>Create your own Salesperson account without individual approval. Visit Plan approvals still follow Odoo policy.</Text>
    <Field label="Odoo URL" value={host} onChange={setHost} placeholder="https://your-odoo.example.com"/>
    <Field label="Database" value={database} onChange={setDatabase} placeholder="odoo_database"/>
    <Field label="Full Name" value={regName} onChange={setRegName} placeholder="Full name"/>
    <Field label="Email" value={email} onChange={setEmail} placeholder="user@example.com"/>
    <Field label="Phone Number" value={regPhone} onChange={setRegPhone} placeholder="+880..." keyboardType="phone-pad"/>
    <Text style={st.fieldLabel}>Role</Text>
    <Text style={[st.body,{marginBottom:12}]}>Salesperson (automatically assigned)</Text>
    <Text style={st.fieldLabel}>Set Password</Text>
    <TextInput value={regPassword} secureTextEntry onChangeText={setRegPassword} style={[st.input,{marginBottom:12}]} placeholder="Enter a password (e.g. 123)" placeholderTextColor="#A2B0B6" autoCapitalize="none"/>
    <Text style={st.fieldLabel}>Confirm Password</Text>
    <TextInput value={regConfirmPassword} secureTextEntry onChangeText={setRegConfirmPassword} style={[st.input,{marginBottom:12}]} placeholder="Re-enter password" placeholderTextColor="#A2B0B6" autoCapitalize="none"/>
    <B onPress={()=>run(async()=>{
      if(!regName.trim()||!email.trim()||!regPhone.trim())throw Error('Enter your name, email and phone.');
      if(!regPassword.trim())throw Error('Enter a password.');
      if(regPassword!==regConfirmPassword)throw Error('Passwords do not match.');
      const result=await Odoo.registerOdooAccount(host,database,{name:regName,email,phone:regPhone,password:regPassword,confirm_password:regConfirmPassword});
      setRegPassword('');setRegConfirmPassword('');setAuthPage('login');notify(result);
    })}>Create Account</B>
    <B variant="ghost" onPress={()=>setAuthPage('login')}>Back to Login</B>
   </Panel>:<Panel>
    <Text style={st.cardTitle}>Forgot Password?</Text>
    <Text style={st.help}>Reset your password on your Odoo server. Enter the email registered in Odoo on the reset page. If reset emails are unavailable, contact your Odoo administrator.</Text>
    <Field label="Odoo URL" value={host} onChange={setHost} placeholder="https://your-odoo.example.com"/>
    <B onPress={()=>run(async()=>{await Linking.openURL(Odoo.odooPasswordResetUrl(host))})}>Open Odoo Password Reset</B>
    <B variant="ghost" onPress={()=>setAuthPage('login')}>Back to Login</B>
   </Panel>}
  </>}
 </>}
 {!!message&&<Text style={st.message}>{message}</Text>}
 </ScrollView></KeyboardAvoidingView>
 <View style={st.nav}>{(['Home','Visits','Tracking','Map','Profile'] as Tab[]).map(t=><Pressable key={t} style={[st.navItem,tab===t&&st.navActive]} onPress={()=>go(t)}><Text style={[st.navIcon,tab===t&&{color:C.green}]}>{icons[t]}</Text><Text style={[st.navText,tab===t&&{color:C.green}]}>{t}</Text></Pressable>)}</View>
 <ZenCoreDialog dialog={dialog} onClose={()=>setDialog(null)}/>
 {busy&&<View style={st.busy}><ActivityIndicator color={C.green} size="large"/></View>}
 </View>;
}
function Info({label,value}:{label:string;value:string}){return <View style={st.info}><Text style={st.muted}>{label}</Text><View style={infoValueStyle}><Text style={[st.body,{textAlign:'right'}]} numberOfLines={2}>{value}</Text></View></View>}
function ZenCoreDialog({dialog,onClose}:{dialog:DialogState|null;onClose:()=>void}){
 if(!dialog)return null;
 const palette=dialog.tone==='success'?{accent:'#2EAB63',soft:'#EAF9EF',icon:'✓'}:
  dialog.tone==='error'?{accent:'#D94B57',soft:'#FFF0F2',icon:'!'}:
  dialog.tone==='warning'?{accent:'#D28B2E',soft:'#FFF6E5',icon:'!'}:
  {accent:'#07518C',soft:'#EAF4FB',icon:'i'};
 return <Modal transparent visible animationType="fade" onRequestClose={onClose}>
  <View style={modalSt.backdrop}>
   <View style={modalSt.card}>
    <View style={[modalSt.icon,{backgroundColor:palette.soft,borderColor:palette.accent}]}><Text style={[modalSt.iconText,{color:palette.accent}]}>{palette.icon}</Text></View>
    <Text style={modalSt.title}>{dialog.title}</Text>
    <Text style={modalSt.message}>{dialog.message}</Text>
    <View style={modalSt.actions}>{dialog.actions.map((action,index)=><Pressable key={`${action.label}-${index}`} onPress={()=>{onClose();if(action.onPress)void action.onPress();}} style={[modalSt.action,action.variant==='light'&&modalSt.actionLight,action.variant==='danger'&&modalSt.actionDanger]}><Text style={[modalSt.actionText,action.variant!=='primary'&&{color:action.variant==='danger'?'#C83E4C':C.blue}]}>{action.label}</Text></Pressable>)}</View>
   </View>
  </View>
 </Modal>;
}
const st=StyleSheet.create({
 root:{flex:1,backgroundColor:C.bg},header:{paddingTop:Platform.OS==='ios'?54:16,paddingBottom:14,paddingHorizontal:20,backgroundColor:'#FBFFFD',flexDirection:'row',alignItems:'center',justifyContent:'space-between',borderBottomColor:C.line,borderBottomWidth:1},brand:{fontSize:24,fontWeight:'900',color:C.blue,letterSpacing:-1},headerSubtitle:{fontSize:11,color:C.muted,marginTop:1},avatar:{height:40,width:40,borderRadius:14,backgroundColor:C.mint,alignItems:'center',justifyContent:'center'},scroll:{padding:19,paddingBottom:38},eyebrow:{color:C.green,fontWeight:'800',fontSize:11,marginBottom:6},heading:{fontSize:19,fontWeight:'800',color:C.text,marginBottom:14},hero:{borderRadius:23,padding:21,marginTop:6,overflow:'hidden',shadowColor:'#07518C',shadowOpacity:.22,shadowRadius:18,elevation:5},heroTitle:{color:C.white,fontSize:23,fontWeight:'900',marginTop:17,marginBottom:9,lineHeight:30,maxWidth:'91%'},heroSub:{color:'#DAF6EC',fontSize:11,marginBottom:16,lineHeight:18},metrics:{flexDirection:'row',justifyContent:'space-between',flexWrap:'wrap',marginTop:15,marginBottom:14},metric:{width:'48%',marginBottom:11},metricIcon:{fontSize:22,color:'#329E57',fontWeight:'700'},metricNumber:{fontSize:26,fontWeight:'900',color:C.text,marginBottom:5},panel:{backgroundColor:C.white,padding:16,marginBottom:13,borderRadius:18,borderWidth:1,borderColor:C.line,shadowOpacity:.04,shadowRadius:10,shadowColor:C.blue,elevation:1},muted:{color:C.muted,fontSize:12,lineHeight:19},body:{fontSize:13,fontWeight:'600',color:C.text},btn:{backgroundColor:C.blue,paddingVertical:13,paddingHorizontal:14,borderRadius:12,alignItems:'center',justifyContent:'center',marginVertical:4},btnLight:{backgroundColor:C.mint,borderWidth:1,borderColor:'#D4ECCC'},btnDanger:{backgroundColor:'#FFF0F2'},btnGhost:{backgroundColor:'transparent'},btnLabel:{color:C.white,fontSize:12,fontWeight:'800',textAlign:'center'},badge:{borderRadius:30,paddingHorizontal:9,paddingVertical:6,alignSelf:'flex-start'},badgeText:{fontWeight:'800',fontSize:10},topLine:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',gap:10,marginBottom:7},actions:{flexDirection:'row',gap:9,justifyContent:'space-between'},cardTitle:{fontWeight:'800',fontSize:14,color:C.text,flexShrink:1},info:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',paddingVertical:11,borderBottomColor:C.line,borderBottomWidth:1,gap:10},nav:{backgroundColor:'#FDFFFE',borderTopWidth:1,borderTopColor:C.line,flexDirection:'row',justifyContent:'space-between',paddingBottom:Platform.OS==='ios'?24:9,paddingTop:10,paddingHorizontal:9},navItem:{alignItems:'center',flex:1,paddingVertical:3,borderRadius:12},navActive:{backgroundColor:'#E8F9EC'},navIcon:{fontSize:22,color:'#93A4AA'},navText:{fontSize:10,fontWeight:'700',color:'#93A4AA',marginTop:4},fieldLabel:{fontSize:12,fontWeight:'800',color:'#466879',marginBottom:6},input:{backgroundColor:'#FAFFFC',borderWidth:1,borderColor:'#DAEAE0',borderRadius:12,paddingHorizontal:12,paddingVertical:12,color:C.text,fontSize:13},chips:{flexDirection:'row',flexWrap:'wrap',gap:7,marginBottom:14},chip:{borderRadius:10,backgroundColor:C.mint,borderWidth:1,borderColor:'#CCE9D0',paddingHorizontal:10,paddingVertical:8},chipActive:{backgroundColor:C.blue,borderColor:C.blue},chipText:{color:C.blue,fontSize:11,fontWeight:'700'},help:{fontSize:11,lineHeight:17,color:C.muted,marginTop:10,marginBottom:7},searchRow:{borderBottomColor:C.line,borderBottomWidth:1,paddingVertical:9,flexDirection:'row',justifyContent:'space-between'},targetRow:{borderTopWidth:1,borderTopColor:C.line,marginTop:12,paddingTop:10,flexDirection:'row',alignItems:'center',justifyContent:'space-between'},total:{backgroundColor:C.mint,borderRadius:12,padding:15,flexDirection:'row',justifyContent:'space-between',alignItems:'center'},totalNumber:{color:'#288A3C',fontWeight:'900',fontSize:18},linkText:{fontSize:12,fontWeight:'700',color:C.blue,marginTop:10},largeNumber:{fontSize:42,fontWeight:'900',color:C.deep,marginVertical:8},message:{marginTop:10,fontSize:11,color:C.amber},ambient:{position:'absolute',top:0,left:0,right:0,bottom:0,opacity:.85},
 dailyCard:{borderRadius:22,marginBottom:13},nextCustomerName:{fontSize:17,fontWeight:'800',color:'#172943',marginTop:6},nextCustomerAddress:{fontSize:12,color:'#587789',marginTop:5},nextCustomerPlan:{fontSize:11,color:'#07518C',fontWeight:'700',marginTop:6},dailyAction:{backgroundColor:'#E9F8EF',borderRadius:13,paddingHorizontal:14,paddingVertical:13,flexDirection:'row',justifyContent:'space-between',marginTop:14},dailyActionLabel:{fontSize:12,color:'#07518C',fontWeight:'800'},dailyCount:{color:'#668290',fontSize:11,fontWeight:'700'},scheduleRow:{flexDirection:'row',alignItems:'center',gap:10,paddingVertical:12,borderBottomColor:'#E7F0ED',borderBottomWidth:1},scheduleDot:{height:9,width:9,borderRadius:5},scheduleTitle:{fontSize:12,fontWeight:'800',color:'#172943'},dailyNetworkRow:{flexDirection:'row',alignItems:'center',gap:7,padding:8,marginBottom:3},networkDot:{height:8,width:8,borderRadius:4},networkText:{fontSize:11,color:'#668290'},
 metricRow:{flexDirection:'row',gap:9,marginVertical:5},liveMetric:{flex:1,backgroundColor:'#FFFFFFCC',borderRadius:14,padding:13,minHeight:86},liveValue:{fontWeight:'900',color:'#07518C',fontSize:19,marginBottom:5},
 trackingSummary:{borderRadius:20,padding:18,marginBottom:14,borderWidth:1,borderColor:'#CDE8DC'},trackingBig:{fontSize:48,fontWeight:'900',color:'#07518C',marginTop:12},trackingStats:{flexDirection:'row',justifyContent:'space-between',marginVertical:16},trackingStatValue:{fontSize:23,fontWeight:'800',color:'#07518C'},
 metricGradient:{borderWidth:1,borderColor:'#DCEEEA',padding:17,overflow:'hidden',minHeight:152,borderRadius:22,shadowColor:'#07518C',shadowOpacity:.08,shadowRadius:12,elevation:2},
 metricSymbol:{width:33,height:33,borderRadius:12,backgroundColor:'#E1F8E5',alignItems:'center',justifyContent:'center',marginBottom:11},
 metricCaption:{color:'#647F8D',fontSize:12,fontWeight:'500'},
 heroKicker:{color:'#D1F7E7',fontSize:10,fontWeight:'800',letterSpacing:1.3,marginBottom:14},
 heroPill:{alignSelf:'flex-start',backgroundColor:'#FFFFFF28',borderWidth:1,borderColor:'#FFFFFF55',borderRadius:22,flexDirection:'row',gap:7,alignItems:'center',paddingVertical:7,paddingHorizontal:11},
 heroPillDot:{height:7,width:7,borderRadius:5},heroPillLabel:{color:'#FFFFFF',fontWeight:'800',fontSize:10,letterSpacing:.5},
 pulseRoot:{height:66,width:66,alignItems:'center',justifyContent:'center',marginLeft:10},
 pulseRing:{position:'absolute',height:62,width:62,borderRadius:40,borderWidth:2,borderColor:'#B0FFC0',backgroundColor:'#77E78B33'},
 pulseCore:{height:44,width:44,borderRadius:24,alignItems:'center',justifyContent:'center',borderWidth:2,borderColor:'#FFFFFFAA'},
 pulseIcon:{fontSize:27,color:'#FFFFFF',fontWeight:'800'},
 heroHeaderRow:{flexDirection:'row',alignItems:'center',justifyContent:'space-between'},
 progressTrack:{height:10,borderRadius:8,backgroundColor:'#DDEAEF',overflow:'hidden',marginTop:13},
 progressFill:{height:'100%',borderRadius:8,backgroundColor:'#70BF36'},
 progressDescription:{fontSize:11,color:'#547583',marginTop:8,fontWeight:'600'},
 profileHeader:{flexDirection:'row',gap:14,alignItems:'center',paddingBottom:18,borderBottomWidth:1,borderBottomColor:'#DFEAE7',marginBottom:10},
 profileAvatar:{height:62,width:62,borderRadius:32,backgroundColor:'#D5EEFF',alignItems:'center',justifyContent:'center'},
 profileAvatarText:{fontSize:23,fontWeight:'900',color:'#07518C'},
 profileName:{fontSize:18,fontWeight:'800',color:'#172943',marginBottom:8},
 heroOrb:{position:'absolute',right:-85,top:-125,width:270,height:270,borderRadius:150,backgroundColor:'#FFFFFF1B'},
 heroOrbSmall:{position:'absolute',right:15,bottom:-65,width:150,height:150,borderRadius:80,backgroundColor:'#FFFFFF16'},
 heroButton:{marginTop:12,minHeight:52,backgroundColor:'#E9FBF0',borderRadius:14,flexDirection:'row',alignItems:'center',justifyContent:'center',borderWidth:1,borderColor:'#CBF3DE'},
 heroButtonText:{color:'#064D80',fontSize:14,fontWeight:'800'},heroButtonArrow:{color:'#064D80',position:'absolute',right:19,fontSize:25,fontWeight:'500'},
 healthCard:{flexDirection:'row',alignItems:'center',gap:12,borderRadius:17,padding:16,marginBottom:11,borderWidth:1,borderColor:'#D7EAE6'},
 healthDot:{width:11,height:11,borderRadius:6},healthTitle:{fontSize:13,color:'#18283F',fontWeight:'800'},healthSub:{fontSize:11,color:'#68808B',marginTop:5,lineHeight:16},
 healthGrid:{flexDirection:'row',gap:10},healthGridItem:{flex:1},healthChip:{fontSize:10,color:'#247C5A',fontWeight:'700',backgroundColor:'#EAF8EC',paddingHorizontal:9,paddingVertical:5,borderRadius:12},
 pageBanner:{padding:19,borderRadius:20,overflow:'hidden',marginBottom:18,minHeight:117,justifyContent:'center'},
 pageBannerOrb:{position:'absolute',height:170,width:170,borderRadius:85,right:-45,top:-72,backgroundColor:'#FFFFFF23'},
 pageBannerEyebrow:{color:'#D9F8E5',fontSize:10,fontWeight:'800',letterSpacing:1.4,marginBottom:7},
 pageBannerTitle:{color:'#FFFFFF',fontSize:24,fontWeight:'900',marginBottom:5},pageBannerSub:{color:'#EAF9F6',fontSize:11,lineHeight:16},
 busy:{...StyleSheet.absoluteFill,backgroundColor:'#FFFFFF99',justifyContent:'center',alignItems:'center'}
});
const modalSt=StyleSheet.create({
 backdrop:{flex:1,backgroundColor:'#07152299',justifyContent:'center',alignItems:'center',padding:24},
 card:{width:'100%',maxWidth:380,backgroundColor:'#FFFFFF',borderRadius:26,padding:24,shadowColor:'#052D48',shadowOpacity:.25,shadowRadius:24,elevation:10},
 icon:{width:54,height:54,borderRadius:18,borderWidth:1.5,alignItems:'center',justifyContent:'center',alignSelf:'center',marginBottom:14},
 iconText:{fontSize:27,fontWeight:'900'},title:{fontSize:21,fontWeight:'900',color:'#172943',textAlign:'center',marginBottom:9},
 message:{fontSize:13,lineHeight:20,color:'#5C7480',textAlign:'center'},actions:{flexDirection:'row',gap:10,marginTop:22},
 action:{flex:1,minHeight:46,borderRadius:14,backgroundColor:'#07518C',alignItems:'center',justifyContent:'center',paddingHorizontal:12},
 actionLight:{backgroundColor:'#EAF8EF',borderWidth:1,borderColor:'#CDE9D4'},actionDanger:{backgroundColor:'#FFF0F2',borderWidth:1,borderColor:'#F6C6CC'},
 actionText:{fontSize:13,fontWeight:'900',color:'#FFFFFF',textAlign:'center'}
});
