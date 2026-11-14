import {pendingGps,markGpsSynced,gpsCount,getPendingStopPlan,setPendingStopPlan} from './storage';
import {batchGps,stopPlanTracking} from './odoo';
import {trackingActive} from './location';

/** An in-flight guard protects against two callers uploading the same UUID concurrently. */
let inFlight: Promise<number> | null = null;

async function flushOnce(): Promise<number> {
  const entries = await pendingGps(100);
  if (!entries.length) return 0;
  const response = await batchGps(entries);
  if (!response || response.ok !== true || !Array.isArray(response.accepted)) {
    throw new Error('Odoo GPS batch acknowledgement is missing or invalid. Records remain pending.');
  }
  const submitted = new Set(entries.map(point => point.id));
  const acknowledged = [...new Set(response.accepted.filter(id => submitted.has(id)))];
  // Only acknowledge UUIDs the server explicitly confirmed from this batch.
  for (const id of acknowledged) await markGpsSynced(id);
  if (response.rejected?.length) {
    const first = response.rejected[0];
    throw new Error(`${response.rejected.length} GPS point(s) rejected; retained in SQLite. ${first.reason || 'Unknown reason'}`);
  }
  if (!acknowledged.length) throw new Error('Odoo acknowledged zero GPS points. Keeping pending data for inspection.');
  return acknowledged.length;
}

export async function flushGps(): Promise<number> {
  if (!inFlight) {
    inFlight = flushOnce().finally(() => { inFlight = null; });
  }
  return inFlight;
}

/** Bounded loop avoids endless background attempts and processes large offline queues. */
export async function flushAllGps(maxBatches = 10): Promise<number> {
  let total = 0;
  for (let index = 0; index < maxBatches; index++) {
    if (!(await gpsCount())) break;
    const count = await flushGps();
    total += count;
    if (!count) break;
  }
  return total;
}


// Server stop must not be blocked by rejected or delayed GPS uploads.
// Backend accepts delayed points for a stopped in-progress tracker and deduplicates UUIDs.
export async function flushPendingPlanStop():Promise<boolean>{
 const planId=await getPendingStopPlan();
 if(!planId)return false;
 // Never stop Odoo while native GPS is still capturing. This also protects
 // against a transient Android stop failure after queuing the stop intent.
 if(await trackingActive())return false;
 const response=await stopPlanTracking(planId);
 if(!response?.ok)throw Error(`Odoo did not confirm stopping Plan #${planId}`);
 await setPendingStopPlan(null);
 return true;
}
