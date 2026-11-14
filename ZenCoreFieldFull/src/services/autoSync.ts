/**
 * Foreground auto-sync controller.
 * - Immediate work on network reconnect / app foreground / login.
 * - Periodic 30-second check while the app is foregrounded, including new GPS points.
 * - Does not mark any GPS point synced until the Odoo batch endpoint acknowledges its UUID.
 * - Mobile OS can suspend JS background work; pending SQLite points sync when the app
 *   resumes. This is NOT a guaranteed background connectivity trigger.
 */
import {AppState, type AppStateStatus} from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import {flushAllGps,flushPendingPlanStop} from './sync';
import {gpsCount,getPendingStopPlan,photoPendingCount} from './storage';
import {flushPhotos} from './photoEvidence';
import {getCookie,verifySession} from './odoo';

export type AutoSyncPhase = 'offline' | 'waiting' | 'syncing' | 'up-to-date' | 'retrying' | 'sign-in-required';
export type AutoSyncSnapshot = {
  phase: AutoSyncPhase;
  pending: number;
  lastSuccessAt: number | null;
  lastError: string | null;
  nextAttemptAt: number | null;
};

const PERIOD_MS = 30000;
const RETRY_BASE_MS = 15000;
const RETRY_MAX_MS = 5 * 60 * 1000;
let initialized = false;
let online = false;
let foreground = AppState.currentState === 'active';
let running = false;
let errors = 0;
let timer: ReturnType<typeof setTimeout> | null = null;
let heartbeat: ReturnType<typeof setInterval> | null = null;
let unlistenNetwork: (()=>void) | null = null;
let appSubscription: {remove():void} | null = null;
let observer: ((snapshot:AutoSyncSnapshot)=>void) | null = null;
let state: AutoSyncSnapshot = {phase:'waiting',pending:0,lastSuccessAt:null,lastError:null,nextAttemptAt:null};

function emit(patch: Partial<AutoSyncSnapshot>) {
  state = {...state,...patch};
  observer?.({...state});
}
function clearAttempt() { if (timer) clearTimeout(timer); timer = null; }
function schedule(delayMs: number) {
  clearAttempt();
  if (!initialized || !online || !foreground) return;
  emit({nextAttemptAt:Date.now()+delayMs});
  timer = setTimeout(() => { timer=null; void syncNow(); }, delayMs);
}
export function getAutoSyncSnapshot() {return {...state};}

async function syncNow() {
  if (!initialized || !online || !foreground || running) return;
  running = true;
  clearAttempt();
  try {
    const pending = await gpsCount();
    emit({pending,nextAttemptAt:null,phase:pending?'syncing':'up-to-date'});
    if (pending || await getPendingStopPlan() || await photoPendingCount()) {
      if (!(await getCookie())) {
        emit({phase:'sign-in-required',lastError:'Sign in to Odoo to upload pending GPS points.'});
        return;
      }
      // This catches server-side session invalidation without losing SQLite data.
      if (!(await verifySession())) {
        emit({phase:'sign-in-required',lastError:'Odoo session expired. Sign in again.'});
        return;
      }
      // Confirm stopped trackers first; a rejected old GPS point must not block restart.
      await flushPendingPlanStop();
      await flushAllGps(10);
      await flushPhotos(3);
    }
    errors = 0;
    const remaining=await gpsCount();
    const stopQueued=await getPendingStopPlan();
    const remainingPhotos=await photoPendingCount();
    emit({phase:(stopQueued||remainingPhotos)?'retrying':'up-to-date',pending:remaining,
      lastSuccessAt:Date.now(),lastError:stopQueued
        ?'Waiting for GPS upload before Odoo stop confirmation.'
        :remainingPhotos?`${remainingPhotos} photo(s) still pending. See Visit Photos for upload errors.`:null});
  } catch (e) {
    errors += 1;
    const delay = Math.min(RETRY_MAX_MS, RETRY_BASE_MS * Math.pow(2,Math.min(errors-1,5)));
    emit({phase:'retrying',pending:await gpsCount().catch(()=>state.pending),lastError:e instanceof Error?e.message:String(e)});
    schedule(delay);
  } finally {
    running = false;
  }
}

export function triggerAutoSync(force = false) {
  if (!initialized || !online || !foreground) return;
  // Keep exponential backoff intact during periodic heartbeats; reconnect/resume
  // and login may override it because the underlying condition may have changed.
  if (!force && state.nextAttemptAt && state.nextAttemptAt > Date.now()) return;
  schedule(0);
}

export function startAutoSync(onChange:(snapshot:AutoSyncSnapshot)=>void):()=>void {
  // App root owns one subscription; replacing an old one prevents duplicate timers.
  stopAutoSync();
  initialized = true;
  observer = onChange;
  onChange({...state});
  unlistenNetwork = NetInfo.addEventListener(next=>{
    const wasOnline=online;
    online = Boolean(next.isConnected && next.isInternetReachable !== false);
    if (!online) { clearAttempt();emit({phase:'offline',nextAttemptAt:null}); }
    else if (!wasOnline) { emit({phase:'waiting'});triggerAutoSync(true); }
  });
  appSubscription = AppState.addEventListener('change',(next:AppStateStatus)=>{
    foreground=next==='active';
    if (foreground) triggerAutoSync(true);
    else clearAttempt();
  });
  heartbeat=setInterval(()=>{if(online && foreground)triggerAutoSync();},PERIOD_MS);
  void gpsCount().then(count=>emit({pending:count})).catch(()=>{});
  return stopAutoSync;
}

export function stopAutoSync(){
  initialized = false;
  clearAttempt();
  if (heartbeat) clearInterval(heartbeat);
  heartbeat=null;
  unlistenNetwork?.();unlistenNetwork=null;
  appSubscription?.remove();appSubscription=null;
  observer=null;
}
