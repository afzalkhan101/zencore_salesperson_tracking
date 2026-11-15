import * as SQLite from 'expo-sqlite';
import type {GpsPoint,Plan} from '../types/models';
let dbPromise:ReturnType<typeof SQLite.openDatabaseAsync>|undefined;
const db=()=>dbPromise??(dbPromise=SQLite.openDatabaseAsync('zencore_field.db'));
export async function initialize(){const d=await db(); await d.execAsync(`PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gps (id TEXT PRIMARY KEY, session TEXT NOT NULL, tracker_id INTEGER NOT NULL DEFAULT 0, plan_id INTEGER NOT NULL DEFAULT 0, latitude REAL NOT NULL, longitude REAL NOT NULL, accuracy REAL NOT NULL, captured_at INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending');
CREATE INDEX IF NOT EXISTS gps_status_time ON gps(status,captured_at);
CREATE TABLE IF NOT EXISTS visit_photos (
 id TEXT PRIMARY KEY, plan_id INTEGER NOT NULL, tracker_id INTEGER,
 customer_id INTEGER, file_uri TEXT NOT NULL, file_name TEXT NOT NULL,
 mime_type TEXT NOT NULL, size INTEGER NOT NULL, captured_at INTEGER NOT NULL,
 note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
 attachment_id INTEGER, message_id INTEGER, error TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS visit_photo_queue ON visit_photos(status,captured_at);`);
 // SQLite schema upgrade for users who already have the V4 database.
 const columns=await d.getAllAsync<{name:string}>('PRAGMA table_info(gps)');
 if(!columns.some(col=>col.name==='plan_id')) await d.execAsync('ALTER TABLE gps ADD COLUMN plan_id INTEGER NOT NULL DEFAULT 0');
 const photoCols=await d.getAllAsync<{name:string}>('PRAGMA table_info(visit_photos)');
 for(const column of ['latitude REAL','longitude REAL','accuracy_m REAL',"location_name TEXT NOT NULL DEFAULT ''","device_name TEXT NOT NULL DEFAULT ''","photo_origin TEXT NOT NULL DEFAULT 'camera'"]){
  const field=column.split(' ')[0];
  if(!photoCols.some(c=>c.name===field))await d.execAsync(`ALTER TABLE visit_photos ADD COLUMN ${column}`);
 }
}
export async function getValue<T>(key:string,fallback:T):Promise<T>{await initialize(); const x=await (await db()).getFirstAsync<{value:string}>('SELECT value FROM kv WHERE key=?',[key]); if(!x)return fallback; try{return JSON.parse(x.value) as T;}catch{return fallback;}}
export async function setValue(key:string,value:unknown){await initialize();await (await db()).runAsync('INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',[key,JSON.stringify(value)]);}
const planStorageKey=(ownerKey='anonymous')=>`plans:${ownerKey||'anonymous'}`;
export const getPlans=(ownerKey='anonymous')=>getValue<Plan[]>(planStorageKey(ownerKey),[]);
export const setPlans=(p:Plan[],ownerKey='anonymous')=>setValue(planStorageKey(ownerKey),p);
export async function addGpsPoint(point:GpsPoint){await initialize();await (await db()).runAsync('INSERT OR IGNORE INTO gps(id,session,tracker_id,plan_id,latitude,longitude,accuracy,captured_at,status) VALUES(?,?,?,?,?,?,?,?,?)',[point.id,point.session,point.trackerId,point.planId,point.latitude,point.longitude,point.accuracy,point.capturedAt,'pending']);}
export async function pendingGps(limit=100){await initialize();return (await db()).getAllAsync<GpsPoint>('SELECT id,session,tracker_id as trackerId,plan_id as planId,latitude,longitude,accuracy,captured_at as capturedAt,status FROM gps WHERE status=? ORDER BY captured_at ASC LIMIT ?',['pending',limit]);}
export async function gpsCount(){await initialize();const v=await (await db()).getFirstAsync<{n:number}>('SELECT COUNT(*) as n FROM gps WHERE status=?',['pending']);return v?.n||0;}
export async function markGpsSynced(id:string){await initialize();await (await db()).runAsync('UPDATE gps SET status=? WHERE id=?',['synced',id]);}
export async function setTrackingSession(session:string|null){await setValue('tracking_session',session);}
export async function getTrackingSession(){const identity=await getTrackingIdentity();return identity!==undefined?(identity?.sessionId||null):getValue<string|null>('tracking_session',null);}

export async function setActiveTracker(id:number|null){await setValue("active_tracker_id",id);}
export async function getActiveTracker(){const identity=await getTrackingIdentity();return identity!==undefined?(identity?.trackerId||null):getValue<number|null>('active_tracker_id',null);}

export async function setActivePlan(id:number|null){await setValue('active_plan_id',id);}
export async function getActivePlan(){const identity=await getTrackingIdentity();return identity!==undefined?(identity?.planId||null):getValue<number|null>('active_plan_id',null);}


// A single atomic SQLite value prevents partial Plan/Tracker/Session metadata
// when Android terminates the process between individual storage writes.
export type TrackingIdentity = {planId:number; trackerId:number; sessionId:string; startedAt:number};
export const getTrackingIdentity = () => getValue<TrackingIdentity|null|undefined>('tracking_identity_v13', undefined);
export async function setTrackingIdentity(value:TrackingIdentity|null){
 if(value===null){const last=await getTrackingIdentity();if(last)await setValue('last_tracking_identity_v16',last);}
 await setValue('tracking_identity_v13',value);
}
export const getLastTrackingIdentity=()=>getValue<TrackingIdentity|null>('last_tracking_identity_v16',null);

// Persist Odoo tracker stop intents across offline periods and app restarts.
// Keep the intent until the server explicitly acknowledges the stop.
export const getPendingStopPlan = () => getValue<number|null>('pending_stop_plan_id', null);
export const setPendingStopPlan = (id:number|null) => setValue('pending_stop_plan_id', id);

export type GpsSummary = {total:number;pending:number;lastCapturedAt:number|null;lastAccuracy:number|null};
export async function gpsSummary(planId:number|null):Promise<GpsSummary>{
 await initialize();
 const d=await db();
 const filter=planId? 'WHERE plan_id = ?':'';
 const args=planId?[planId]:[];
 const total=await d.getFirstAsync<{total:number;pending:number}>(
   `SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END),0) AS pending FROM gps ${filter}`,args);
 const last=await d.getFirstAsync<{captured_at:number;accuracy:number}>(
   `SELECT captured_at,accuracy FROM gps ${filter} ORDER BY captured_at DESC LIMIT 1`,args);
 return {total:total?.total??0,pending:total?.pending??0,lastCapturedAt:last?.captured_at??null,lastAccuracy:last?.accuracy??null};
}

/** Actual recorded distance from successive GPS fixes in THIS tracking session.
 * Accuracy and speed filters reduce stationary jitter; this is GPS route distance,
 * not road-routed distance and not guaranteed survey-grade mileage. */
export type TrackingMetrics={distanceMeters:number;durationMs:number;accuracyMeters:number|null;
 latestLat:number|null;latestLng:number|null;lastFixAt:number|null;acceptedFixes:number};
export async function trackingMetrics(identity:TrackingIdentity|null):Promise<TrackingMetrics>{
 const empty:TrackingMetrics={distanceMeters:0,durationMs:0,accuracyMeters:null,latestLat:null,latestLng:null,lastFixAt:null,acceptedFixes:0};
 if(!identity)return empty;
 await initialize();
 const points=await (await db()).getAllAsync<{lat:number;lng:number;acc:number;time:number}>(
  'SELECT latitude AS lat,longitude AS lng,accuracy AS acc,captured_at AS time FROM gps WHERE session=? AND plan_id=? AND tracker_id=? ORDER BY captured_at,id',
  [identity.sessionId,identity.planId,identity.trackerId]);
 let previous:typeof points[number]|null=null;let distance=0;let valid=0;
 const rad=(v:number)=>v*Math.PI/180;
 for(const p of points){
  if(!Number.isFinite(p.lat)||!Number.isFinite(p.lng)||p.lat < -90||p.lat > 90||p.lng < -180||p.lng > 180)continue;
  if(!Number.isFinite(p.acc)||p.acc<0||p.acc>50)continue;
  valid++;
  if(previous){
   const dLat=rad(p.lat-previous.lat),dLng=rad(p.lng-previous.lng);
   const h=Math.sin(dLat/2)**2+Math.cos(rad(previous.lat))*Math.cos(rad(p.lat))*Math.sin(dLng/2)**2;
   const delta=6371000*2*Math.atan2(Math.sqrt(h),Math.sqrt(Math.max(0,1-h)));
   const secs=(p.time-previous.time)/1000;
   const jitterFloor=Math.max(12,(p.acc+previous.acc)*0.65);
   if(secs>0 && delta>=jitterFloor && delta/secs<=45)distance+=delta;
  }
  previous=p;
 }
 const last=points.length?points[points.length-1]:null;
 return {distanceMeters:distance,durationMs:Math.max(0,Date.now()-identity.startedAt),
  accuracyMeters:last?.acc!=null&&last.acc>=0?last.acc:null,
  latestLat:last?.lat??null,latestLng:last?.lng??null,lastFixAt:last?.time??null,acceptedFixes:valid};
}
// V14: persistent photo evidence queue. Never discard a file until the Odoo
// acknowledgement is stored. Attachment upload is separate from GPS upload.
export type VisitPhoto = {
  id:string; planId:number; trackerId:number|null; customerId:number|null;
  fileUri:string; fileName:string; mimeType:string; size:number;
  capturedAt:number; note:string; status:'pending'|'uploaded';
  attachmentId:number|null; messageId:number|null; error:string;
  latitude?:number|null;longitude?:number|null;accuracyM?:number|null;locationName?:string;deviceName?:string;photoOrigin?:'camera'|'gallery';
};
export async function addVisitPhoto(photo:VisitPhoto){
  await initialize();
  await (await db()).runAsync(`INSERT INTO visit_photos
  (id,plan_id,tracker_id,customer_id,file_uri,file_name,mime_type,size,captured_at,note,status,latitude,longitude,accuracy_m,location_name,device_name,photo_origin)
  VALUES(?,?,?,?,?,?,?,?,?,?,'pending',?,?,?,?,?,?)`,
  [photo.id,photo.planId,photo.trackerId,photo.customerId,photo.fileUri,photo.fileName,photo.mimeType,photo.size,photo.capturedAt,photo.note,photo.latitude??null,photo.longitude??null,photo.accuracyM??null,photo.locationName||'',photo.deviceName||'',photo.photoOrigin||'camera']);
}
export async function getVisitPhotos(planId:number):Promise<VisitPhoto[]>{
 await initialize();return (await db()).getAllAsync<VisitPhoto>(`SELECT id,plan_id AS planId,tracker_id AS trackerId,customer_id AS customerId,
 file_uri AS fileUri,file_name AS fileName,mime_type AS mimeType,size,captured_at AS capturedAt,note,status,
 attachment_id AS attachmentId,message_id AS messageId,error,latitude,longitude,accuracy_m AS accuracyM,location_name AS locationName,device_name AS deviceName,photo_origin AS photoOrigin FROM visit_photos WHERE plan_id=? ORDER BY captured_at DESC`,[planId]);
}
export async function pendingVisitPhotos(limit=3):Promise<VisitPhoto[]>{
 await initialize();return (await db()).getAllAsync<VisitPhoto>(`SELECT id,plan_id AS planId,tracker_id AS trackerId,customer_id AS customerId,
 file_uri AS fileUri,file_name AS fileName,mime_type AS mimeType,size,captured_at AS capturedAt,note,status,
 attachment_id AS attachmentId,message_id AS messageId,error,latitude,longitude,accuracy_m AS accuracyM,location_name AS locationName,device_name AS deviceName,photo_origin AS photoOrigin FROM visit_photos WHERE status='pending' ORDER BY captured_at LIMIT ?`,[limit]);
}
export async function photoPendingCount():Promise<number>{await initialize(); const a=await (await db()).getFirstAsync<{n:number}>("SELECT COUNT(*) AS n FROM visit_photos WHERE status='pending'");return a?.n||0;}
export async function markPhotoUploaded(id:string,attachmentId:number,messageId:number){
 await initialize();await (await db()).runAsync("UPDATE visit_photos SET status='uploaded',attachment_id=?,message_id=?,error='' WHERE id=?",[attachmentId,messageId,id]);
}
export async function setPhotoError(id:string,reason:string){await initialize();await (await db()).runAsync('UPDATE visit_photos SET error=? WHERE id=?',[reason.slice(0,350),id]);}
export async function removePendingPhoto(id:string){await initialize();await (await db()).runAsync("DELETE FROM visit_photos WHERE id=? AND status='pending'",[id]);}


// V17 read-only map source. Never changes GPS statuses or the sync queue.
// Only recorded points for one exact Plan/Tracker/Session are included.
export type RouteFix = { latitude:number; longitude:number; accuracy:number; capturedAt:number };
export async function getRecordedRoute(identity:TrackingIdentity|null, limit=1500):Promise<RouteFix[]> {
 if (!identity) return [];
 await initialize();
 const rows=await (await db()).getAllAsync<RouteFix>(
  `SELECT latitude, longitude, accuracy, captured_at AS capturedAt FROM
    (SELECT latitude, longitude, accuracy, captured_at, id FROM gps
     WHERE plan_id=? AND tracker_id=? AND session=?
     ORDER BY captured_at DESC, id DESC LIMIT ?)
   ORDER BY capturedAt ASC`,
  [identity.planId,identity.trackerId,identity.sessionId,Math.min(Math.max(1,limit),3000)]
 );
 return rows.filter(p=>Number.isFinite(p.latitude)&&Math.abs(p.latitude)<=90&&
  Number.isFinite(p.longitude)&&Math.abs(p.longitude)<=180&&
  Number.isFinite(p.accuracy)&&p.accuracy>=0&&p.accuracy<=100);
}


/** V22: sum verified visible GPS movement across the signed-in user's server plans.
 * Never delete/modify GPS fixes or sync status; a displayed distance is an
 * estimate based only on recorded movement (missing GPS gaps are excluded).
 * Plan IDs are sourced from authenticated Odoo plan listing to avoid counting
 * another Odoo account's records on a shared phone.
 */
export async function localDistanceForPlans(planIds:number[]):Promise<number>{
 const ids=[...new Set(planIds.filter(id=>Number.isInteger(id)&&id>0))];
 if(!ids.length)return 0;
 await initialize();
 const {cleanDisplayedRoute,haversineMeters}=await import('./routeQuality');
 const d=await db();
 let total=0;
 for(const id of ids.slice(0,200)){
  const sessions=await d.getAllAsync<{session:string;trackerId:number}>(
   'SELECT DISTINCT session, tracker_id AS trackerId FROM gps WHERE plan_id=?',[id]);
  for(const item of sessions.slice(0,100)){
   const rows=await d.getAllAsync<RouteFix>(
    'SELECT latitude,longitude,accuracy,captured_at AS capturedAt FROM gps WHERE plan_id=? AND tracker_id=? AND session=? ORDER BY captured_at,id LIMIT 10000',
    [id,item.trackerId,item.session]);
   for(const seg of cleanDisplayedRoute(rows)){
    for(let i=1;i<seg.length;i++)total+=haversineMeters(seg[i-1],seg[i]);
   }
  }
 }
 return Math.round(total)/1000;
}
