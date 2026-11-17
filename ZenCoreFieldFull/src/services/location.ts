import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';
import {addGpsPoint,getTrackingSession,getActiveTracker,getActivePlan,getTrackingIdentity,setTrackingIdentity} from './storage';
import type {GpsPoint} from '../types/models';

const TASK='ZENCORE_FIELD_BACKGROUND_LOCATION';
const GPS_CAPTURE_INTERVAL_MS=2000;
const GPS_MIN_DISTANCE_M=1;
const GPS_UPLOAD_INTERVAL_MS=5000;
const uid=()=>`${Date.now()}-${Math.random().toString(36).slice(2)}`;
const rad=(value:number)=>value*Math.PI/180;

type LastFix={latitude:number;longitude:number;capturedAt:number};
let foregroundSubscription:Location.LocationSubscription|null=null;
let foregroundSession:string|null=null;
const lastFixBySession=new Map<string,LastFix>();
let gpsUploadTimer:ReturnType<typeof setTimeout>|null=null;
let lastGpsUploadAttemptAt=0;

export type TrackingCaptureMode='background'|'foreground'|'stopped';
export type TrackingInspection={
 nativeStarted:boolean;
 foregroundStarted:boolean;
 planId:number|null;
 trackerId:number|null;
 sessionId:string|null;
 active:boolean;
 needsRecovery:boolean;
 captureMode:TrackingCaptureMode;
};

function distanceMeters(a:LastFix,b:Location.LocationObject){
 const dLat=rad(b.coords.latitude-a.latitude);
 const dLng=rad(b.coords.longitude-a.longitude);
 const h=Math.sin(dLat/2)**2+
  Math.cos(rad(a.latitude))*Math.cos(rad(b.coords.latitude))*Math.sin(dLng/2)**2;
 return 6371000*2*Math.atan2(Math.sqrt(h),Math.sqrt(Math.max(0,1-h)));
}

function validLocation(location:Location.LocationObject){
 const {latitude,longitude,accuracy}=location.coords;
 return Number.isFinite(latitude)&&Math.abs(latitude)<=90&&
  Number.isFinite(longitude)&&Math.abs(longitude)<=180&&
  (accuracy==null||Number.isFinite(accuracy));
}

/**
 * The foreground watch and Android background task can both receive the same
 * native fix while the app is open. Retain the first one and ignore only a
 * near-identical duplicate; real movement always stays in the SQLite queue.
 */
export async function persistLocation(location:Location.LocationObject,session:string){
 if(!validLocation(location))return false;
 const capturedAt=location.timestamp||Date.now();
 const previous=lastFixBySession.get(session);
 // Ask Android for a fix every two seconds, but do not manufacture route
 // movement while the device remains inside one metre of its last stored fix.
 // This is deliberately a capture rule, not a timer stop: the native watcher
 // stays alive until the salesperson explicitly stops tracking.
 if(previous&&distanceMeters(previous,location)<GPS_MIN_DISTANCE_M)return false;
 const trackerId=await getActiveTracker();
 const planId=await getActivePlan();
 if(!trackerId||!planId)return false;
 const point:GpsPoint={
  id:uid(),session,trackerId,planId,
  latitude:location.coords.latitude,longitude:location.coords.longitude,
  accuracy:location.coords.accuracy??-1,capturedAt,status:'pending',
 };
 await addGpsPoint(point);
 lastFixBySession.set(session,{latitude:point.latitude,longitude:point.longitude,capturedAt});
 // Keep 2-second capture local. Odoo receives a bounded batch every five
 // seconds, avoiding a network request for every individual GPS callback.
 scheduleGpsUpload();
 return true;
}

async function flushOneBackgroundBatch(force=false){
 if(!force&&Date.now()-lastGpsUploadAttemptAt<GPS_UPLOAD_INTERVAL_MS)return;
 lastGpsUploadAttemptAt=Date.now();
 try {const {flushAllGps}=await import('./sync');await flushAllGps(1);}
 catch(error){console.warn('[ZenCore GPS] Background upload retained for retry',error);}
}

function scheduleGpsUpload(){
 if(gpsUploadTimer)return;
 const elapsed=Date.now()-lastGpsUploadAttemptAt;
 const delay=lastGpsUploadAttemptAt
  ?Math.max(0,GPS_UPLOAD_INTERVAL_MS-elapsed)
  :GPS_UPLOAD_INTERVAL_MS;
 gpsUploadTimer=setTimeout(()=>{
  gpsUploadTimer=null;
  void flushOneBackgroundBatch(true);
 },delay);
}

// Expo Go on Android deliberately does not provide TaskManager.  Defining the
// native task must therefore never prevent the foreground watcher from booting.
try{
 if(!TaskManager.isTaskDefined(TASK)){
  TaskManager.defineTask(TASK,async ({data,error})=>{
  if(error){console.warn('[ZenCore GPS] Background task error',error.message);return;}
  const session=await getTrackingSession();
  if(!session)return;
  const locations=(data as {locations?:Location.LocationObject[]}|undefined)?.locations||[];
  for(const item of locations)await persistLocation(item,session);
  // Do not lose a live route merely because the React foreground timer is asleep.
  await flushOneBackgroundBatch();
  });
 }
}catch(error){
 console.warn('[ZenCore GPS] Background task is unavailable in this client; foreground GPS remains enabled.',error);
}

async function taskManagerAvailable(){
 try{return await TaskManager.isAvailableAsync();}
 catch{return false;}
}

async function stopForegroundWatch(){
 if(foregroundSubscription){foregroundSubscription.remove();foregroundSubscription=null;}
 foregroundSession=null;
}

async function ensureForegroundWatch(session:string){
 if(foregroundSubscription&&foregroundSession===session)return true;
 await stopForegroundWatch();
 try{
  foregroundSubscription=await Location.watchPositionAsync({
   accuracy:Location.Accuracy.High,
   timeInterval:GPS_CAPTURE_INTERVAL_MS,
   distanceInterval:GPS_MIN_DISTANCE_M,
   mayShowUserSettingsDialog:true,
  },location=>{void persistLocation(location,session);});
  foregroundSession=session;
  return true;
 }catch(error){
  console.warn('[ZenCore GPS] Foreground watcher could not start',error);
  await stopForegroundWatch();
  return false;
 }
}

async function restoreForegroundWatch(identity:Awaited<ReturnType<typeof getTrackingIdentity>>){
 if(!identity||foregroundSubscription)return Boolean(foregroundSubscription);
 const permission=await Location.getForegroundPermissionsAsync();
 if(permission.status!=='granted')return false;
 return ensureForegroundWatch(identity.sessionId);
}

/** Truthful device state: a saved plan ID alone is never presented as recording. */
export async function inspectTracking():Promise<TrackingInspection>{
 const nativeStarted=await Location.hasStartedLocationUpdatesAsync(TASK).catch(()=>false);
 const identity=await getTrackingIdentity();
 const planId=identity?.planId??null;
 const trackerId=identity?.trackerId??null;
 const sessionId=identity?.sessionId??null;
 let foregroundStarted=Boolean(foregroundSubscription&&foregroundSession===sessionId);
 // Expo Go cannot run the background task on Android. Restore foreground
 // capture after a fast refresh/relaunch so testing still records real GPS.
 if(identity&&!nativeStarted&&!foregroundStarted)foregroundStarted=await restoreForegroundWatch(identity);
 const hasIdentity=Boolean(planId&&trackerId&&sessionId);
 const active=Boolean(hasIdentity&&(nativeStarted||foregroundStarted));
 return {
  nativeStarted,foregroundStarted,planId,trackerId,sessionId,active,
  needsRecovery:Boolean((nativeStarted&&!hasIdentity)||(!nativeStarted&&!foregroundStarted&&hasIdentity)),
  captureMode:nativeStarted?'background':foregroundStarted?'foreground':'stopped',
 };
}

export async function startTracking(trackerId:number,planId:number){
 if(!Number.isInteger(trackerId)||trackerId<=0||!Number.isInteger(planId)||planId<=0)
  throw Error('Valid Odoo Tracker ID and Visit Plan ID are required.');
 const prior=await inspectTracking();
 if(prior.active){
  if(prior.planId===planId&&prior.trackerId===trackerId)return prior.sessionId!;
  throw Error(`Tracking is already active for Plan #${prior.planId}. Stop it before starting another.`);
 }
 if(prior.nativeStarted||prior.needsRecovery)
  throw Error('Device tracking state requires repair. Use Repair Tracking State before starting another Plan.');
 const foregroundPermission=await Location.requestForegroundPermissionsAsync();
 if(foregroundPermission.status!=='granted')
  throw Error('Location permission denied. Enable precise location in Android settings.');

 const sessionId=uid();
 // Store identity before callbacks can arrive; a GPS sample can never be routed
 // to another plan/tracker after a restart.
 await setTrackingIdentity({planId,trackerId,sessionId,startedAt:Date.now()});
 lastGpsUploadAttemptAt=Date.now();
 const foregroundStarted=await ensureForegroundWatch(sessionId);
 if(!foregroundStarted){await setTrackingIdentity(null);throw Error('GPS listener could not start. Turn on Location and try again.');}

 // A native development/release build has the required foreground-service and
 // background permissions from app.json. Expo Go does not expose TaskManager on
 // Android, so it still records reliably while open instead of failing Start.
 const canUseBackground=await taskManagerAvailable();
 if(canUseBackground){
  try{
   let backgroundPermission=await Location.getBackgroundPermissionsAsync();
   if(backgroundPermission.status!=='granted')backgroundPermission=await Location.requestBackgroundPermissionsAsync();
   if(backgroundPermission.status==='granted'){
    await Location.startLocationUpdatesAsync(TASK,{
     accuracy:Location.Accuracy.High,
     timeInterval:GPS_CAPTURE_INTERVAL_MS,
     distanceInterval:GPS_MIN_DISTANCE_M,
     pausesUpdatesAutomatically:false,
     showsBackgroundLocationIndicator:true,
     foregroundService:{
      notificationTitle:'ZenCore Field tracking active',
      notificationBody:`Recording Visit Plan #${planId}`,
      notificationColor:'#07518C',
     },
    });
   }else{
    console.warn('[ZenCore GPS] Background location was not granted; foreground tracking remains active.');
   }
  }catch(error){
   // A foreground watcher is already healthy. Keep recording rather than
   // incorrectly rolling back a verified Odoo tracker because only background
   // permission/service setup is unavailable.
   console.warn('[ZenCore GPS] Background service unavailable; foreground tracking continues.',error);
  }
 }
 try{
  const first=await Location.getCurrentPositionAsync({accuracy:Location.Accuracy.High,mayShowUserSettingsDialog:true});
  await persistLocation(first,sessionId);
 }catch(error){console.warn('[ZenCore GPS] Initial fix unavailable; watch remains active.',error);}
 return sessionId;
}

export async function stopTracking(){
 // Clear identity only after every running native capture mechanism stops.
 if(await Location.hasStartedLocationUpdatesAsync(TASK).catch(()=>false))await Location.stopLocationUpdatesAsync(TASK);
 if(gpsUploadTimer){clearTimeout(gpsUploadTimer);gpsUploadTimer=null;}
 await stopForegroundWatch();
 await setTrackingIdentity(null);
}

/** Recover inconsistent state without manufacturing a Plan/Tracker ID. */
export async function repairTracking(){
 const before=await inspectTracking();
 if(before.active)throw Error('Tracking is active and healthy. Use Stop Plan Tracking instead.');
 if(before.nativeStarted)await Location.stopLocationUpdatesAsync(TASK);
 await stopForegroundWatch();
 await setTrackingIdentity(null);
 return before;
}

export const trackingActive=async()=> (await inspectTracking()).active;
export async function currentGps(){
 const permission=await Location.requestForegroundPermissionsAsync();
 if(permission.status!=='granted')throw Error('Location permission denied');
 return Location.getCurrentPositionAsync({accuracy:Location.Accuracy.High,mayShowUserSettingsDialog:true});
}
