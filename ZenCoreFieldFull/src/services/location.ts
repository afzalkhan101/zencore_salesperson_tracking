import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';
import {addGpsPoint,getTrackingSession,getActiveTracker,getActivePlan,getTrackingIdentity,setTrackingIdentity} from './storage';
import type {GpsPoint} from '../types/models';
const TASK='ZENCORE_FIELD_BACKGROUND_LOCATION';
const uid=()=>`${Date.now()}-${Math.random().toString(36).slice(2)}`;
export async function persistLocation(location:Location.LocationObject,session:string){
 const trackerId=await getActiveTracker();const planId=await getActivePlan();if(!trackerId||!planId)return;
 const point:GpsPoint={id:uid(),session,trackerId,planId,latitude:location.coords.latitude,longitude:location.coords.longitude,accuracy:location.coords.accuracy??-1,capturedAt:location.timestamp||Date.now(),status:'pending'};
 await addGpsPoint(point);
 // Foreground: initiate sync immediately, rather than waiting for the 30s heartbeat.
 // When the OS suspends JS, SQLite retains the point for reconnect/resume.
 try { const {triggerAutoSync}=await import('./autoSync');triggerAutoSync(true); }
 catch(err){console.warn('[ZenCore GPS] Sync will retry on resume',err);}
}
TaskManager.defineTask(TASK,async ({data,error})=>{
 if(error)return;
 const session=await getTrackingSession();if(!session)return;
 const locations=(data as {locations?:Location.LocationObject[]}|undefined)?.locations||[];
 for(const item of locations)await persistLocation(item,session);
});
/** Truthful device state: a running native task alone is NOT a valid plan session. */
export async function inspectTracking(){
 const nativeStarted=await Location.hasStartedLocationUpdatesAsync(TASK);
 const planId=await getActivePlan();
 const trackerId=await getActiveTracker();
 const sessionId=await getTrackingSession();
 const hasIdentity=Boolean(planId && trackerId && sessionId);
 return {
  nativeStarted,planId,trackerId,sessionId,
  active:Boolean(nativeStarted && hasIdentity),
  needsRecovery:Boolean((nativeStarted && !hasIdentity)||(!nativeStarted && hasIdentity)),
 };
}

export async function startTracking(trackerId:number,planId:number){
 if(!Number.isInteger(trackerId)||trackerId<=0||!Number.isInteger(planId)||planId<=0)
  throw Error('Valid Odoo Tracker ID and Visit Plan ID are required.');
 const prior=await inspectTracking();
 if(prior.active){
  if(prior.planId===planId && prior.trackerId===trackerId) return prior.sessionId!;
  throw Error(`Tracking is already active for Plan #${prior.planId}. Stop it before starting another.`);
 }
 if(prior.nativeStarted || prior.needsRecovery)
  throw Error('Device tracking state requires repair. Use Repair Tracking State before starting another Plan.');
 const fg=await Location.requestForegroundPermissionsAsync();
 if(fg.status!=='granted')throw Error('Location permission denied. Enable precise location in Android settings.');
 const bg=await Location.requestBackgroundPermissionsAsync();
 if(bg.status!=='granted')throw Error('Allow background location for tracking while the screen is locked.');
 const sessionId=uid();
 // One SQLite write is authoritative; older keys are read only for V12 migration.
 await setTrackingIdentity({planId,trackerId,sessionId,startedAt:Date.now()});
 try{
  await Location.startLocationUpdatesAsync(TASK,{
   accuracy:Location.Accuracy.High,timeInterval:10000,distanceInterval:10,
   pausesUpdatesAutomatically:false,showsBackgroundLocationIndicator:true,
   foregroundService:{notificationTitle:'ZenCore Field tracking active',notificationBody:`Recording Visit Plan #${planId}`,notificationColor:'#07518C'},
  });
  if(!(await Location.hasStartedLocationUpdatesAsync(TASK)))throw Error('Android did not start the location service.');
 }catch(e){await setTrackingIdentity(null);throw e;}
 try{
  const first=await Location.getCurrentPositionAsync({accuracy:Location.Accuracy.High});
  await persistLocation(first,sessionId);
 }catch(err){console.warn('[ZenCore GPS] Initial fix unavailable:',err);}
 return sessionId;
}

export async function stopTracking(){
 // Clear identity ONLY after native capture stops. If stop fails, keep state
 // so user can retry rather than losing the tracker association.
 if(await Location.hasStartedLocationUpdatesAsync(TASK))await Location.stopLocationUpdatesAsync(TASK);
 await setTrackingIdentity(null);
}

/** Recover inconsistent state without manufacturing a Plan/Tracker ID. */
export async function repairTracking(){
 const before=await inspectTracking();
 if(before.active)throw Error('Tracking is active and healthy. Use Stop Plan Tracking instead.');
 if(before.nativeStarted)await Location.stopLocationUpdatesAsync(TASK);
 await setTrackingIdentity(null);
 return before;
}

export const trackingActive=()=>Location.hasStartedLocationUpdatesAsync(TASK);
export async function currentGps(){const permission=await Location.requestForegroundPermissionsAsync();if(permission.status!=='granted')throw Error('Location permission denied');return Location.getCurrentPositionAsync({accuracy:Location.Accuracy.High});}
