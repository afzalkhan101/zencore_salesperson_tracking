/**
 * ZenCore Field Odoo transport v4 – no third-party native cookie module.
 * React Native fetch with credentials: 'include' relies on the platform's cookie jar.
 * Verify authenticated session with Odoo after login; do NOT assume it persisted.
 * All server responses are read as text first to diagnose HTML/proxy redirects.
 * Never log passwords, session IDs, response bodies, or complete query strings.
 */
import * as SecureStore from 'expo-secure-store';
import type { Plan, Customer } from '../types/models';

const HOST_KEY = 'zencore_odoo_host_v4';
const LOGGED_IN_KEY = 'zencore_odoo_session_checked_v4';
const TIMEOUT_MS = 30000;
const VERSION = 'ZENCORE_TRANSPORT_V4_NO_COOKIE_MODULE';
type Method = 'GET' | 'POST';
type RecordAny = Record<string, unknown>;
type SessionInfo = {uid?: number | null; name?: string; username?: string};
type GpsPointInput = {id:string;session:string;trackerId:number;planId:number;latitude:number;longitude:number;accuracy:number;capturedAt:number};

/**
 * A physical Android device can reach the developer machine only through
 * `adb reverse`.  That maps the device loopback address to Odoo running on
 * the machine, so it is safe to allow this one HTTP-only case in a dev build.
 * Every other connection (and every production build) remains HTTPS-only.
 */
function isAdbReverseDevelopmentUrl(uri:URL):boolean {
  return __DEV__
    && uri.protocol === 'http:'
    && ['localhost', '127.0.0.1', '[::1]'].includes(uri.hostname);
}

function hostOrigin(input:string):string {
  const str = input.trim();
  if (!str) throw Error('Enter the Odoo HTTPS URL (or http://127.0.0.1:<port> for local Android development).');
  let uri: URL;
  try {uri=new URL(str);} catch {throw Error('Invalid URL. Use https://your-database.odoo.com');}
  if (uri.protocol !== 'https:' && !isAdbReverseDevelopmentUrl(uri)) {
    throw Error('An HTTPS Odoo server URL is required. In a development build, http://127.0.0.1:<port> is allowed only with adb reverse.');
  }
  if (!uri.hostname || uri.username || uri.password) throw Error('Invalid Odoo URL. Do not put credentials in the URL.');
  if (uri.pathname !== '/' && uri.pathname !== '') throw Error('Use the root Odoo URL only, without /web/login or another path.');
  if (uri.search || uri.hash) throw Error('Remove URL query parameters and fragments.');
  return uri.origin;
}
function rpc(params:RecordAny={}) {return {jsonrpc:'2.0',method:'call',params,id:Date.now()};}
function endpointName(path:string) {return path.split('?')[0];}
function serverError(payload:unknown):string {
  if (typeof payload==='string') return payload;
  if (!payload || typeof payload!=='object') return 'Odoo returned an unknown error.';
  const error = payload as RecordAny;
  const extra = error.data && typeof error.data==='object' ? error.data as RecordAny : {};
  return String(extra.message || error.message || 'Odoo returned an error.');
}
async function http<T>(base:string,path:string,method:Method,body?:unknown):Promise<T> {
  if (!path.startsWith('/') || path.startsWith('//')) throw Error('Invalid API path.');
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),TIMEOUT_MS);
  try {
    const response=await fetch(base+path,{
      method,
      credentials:'include',
      headers:{'Content-Type':'application/json','Accept':'application/json'},
      ...(method==='POST'?{body:JSON.stringify(body??{})}:{}),
      signal:controller.signal,
    });
    const raw=await response.text();
    const contentType=response.headers.get('content-type')||'unknown';
    // Response URL may have followed a redirect to a web login or error page.
    let finalDestination='unknown';
    try {const u=new URL(response.url);finalDestination=u.origin+u.pathname;} catch {}
    if (__DEV__) console.log(`[${VERSION}] ${method} ${endpointName(path)} status=${response.status} type=${contentType} redirected=${response.redirected}`);
    const trimmed=raw.trimStart();
    if (response.status === 404 && path.startsWith('/zencore/field/')) {
      throw Error(`Odoo Mobile Bridge endpoint missing (HTTP 404): ${endpointName(path)}. Install/upgrade zencore_field_mobile_bridge version 19.0.3.0.0 on the SAME Odoo database and host used in Profile, then restart/update the Odoo registry. Updating only the mobile APK cannot create server endpoints.`);
    }
    if (trimmed.startsWith('<') || !trimmed || (!contentType.toLowerCase().includes('json') && !/^[\[{]/.test(trimmed))) {
      throw Error(`Odoo returned HTML/non-JSON (HTTP ${response.status}). Endpoint: ${endpointName(path)}. Final URL: ${finalDestination}. Check Odoo root URL, database routing, reverse proxy and web-login redirects.`);
    }
    let parsed:RecordAny;
    try {parsed=JSON.parse(raw) as RecordAny;}
    catch {throw Error(`Odoo returned malformed JSON (HTTP ${response.status}) at ${endpointName(path)}.`);}
    if (parsed.error) throw Error(`Odoo: ${serverError(parsed.error)}`);
    if (!response.ok) throw Error(`Odoo HTTP ${response.status}: ${serverError(parsed.message||parsed.error)}`);
    const value=(parsed.jsonrpc==='2.0' && Object.prototype.hasOwnProperty.call(parsed,'result'))?parsed.result:parsed;
    if (value && typeof value==='object') {
      const data=value as RecordAny;
      if (data.ok===false || data.status==='unauthorized') throw Error(String(data.message||data.error||'Odoo API rejected this request.'));
    }
    return value as T;
  } catch(e:unknown) {
    if (e instanceof Error && e.name==='AbortError') throw Error('Odoo request timeout. Check network, proxy and server availability.');
    if (e instanceof Error && /Network request failed|Failed to fetch/i.test(e.message)) throw Error('Cannot connect to Odoo. Verify HTTPS certificate, hostname and internet.');
    throw e;
  } finally {clearTimeout(timer);}
}
async function sessionInfo(base:string):Promise<SessionInfo> {
  return http<SessionInfo>(base,'/web/session/get_session_info','POST',rpc({}));
}
export async function getHost():Promise<string> {return (await SecureStore.getItemAsync(HOST_KEY))||'';}
/** Legacy UI compatibility: this returns a verified-login marker, NOT an actual cookie. */
export async function getCookie():Promise<string> {return (await SecureStore.getItemAsync(LOGGED_IN_KEY))==='1'?'native-http-session':'';}
export async function verifySession():Promise<boolean> {
  const base=await getHost();
  if (!base || !(await getCookie())) return false;
  try {
    const info=await sessionInfo(base);
    if(info?.uid) return true;
    // Reachable server explicitly denies an existing session.
    await SecureStore.deleteItemAsync(LOGGED_IN_KEY);
  } catch {
    // Network errors must not delete offline login state; queue remains local.
  }
  return false;
}
export async function login(host:string,database:string,username:string,password:string):Promise<string> {
  if (__DEV__) console.log(`[${VERSION}] login() executed`);
  const base=hostOrigin(host);
  const db=database.trim(), user=username.trim();
  if (!db||!user||!password) throw Error('Enter database, login/email and password.');
  // Prevent a previous device-side login marker from being mistaken for a new session.
  await SecureStore.deleteItemAsync(LOGGED_IN_KEY);
  const result=await http<SessionInfo>(base,'/web/session/authenticate','POST',rpc({db,login:user,password}));
  if (!result?.uid) throw Error('Odoo did not accept these credentials. Check database, username, password, and MFA/SSO requirements.');
  let verified:SessionInfo;
  try {verified=await sessionInfo(base);} catch(e) {
    throw Error(`Credentials accepted, but the Odoo session could not be reused by the mobile HTTP client. ${e instanceof Error?e.message:String(e)} Use a dedicated token-auth bridge if your environment does not persist session cookies.`);
  }
  if (!verified?.uid || verified.uid!==result.uid) throw Error('Credentials accepted but session verification failed. The server session cookie was not retained or database routing changed.');
  await SecureStore.setItemAsync(HOST_KEY,base);
  await SecureStore.setItemAsync(LOGGED_IN_KEY,'1');
  return verified.name||result.name||user;
}
export async function logout():Promise<void> {
  const base=await getHost();
  if (base) {try {await http(base,'/web/session/destroy','POST',rpc({}));} catch { /* offline sign-out */ }}
  await SecureStore.deleteItemAsync(LOGGED_IN_KEY);
  await SecureStore.deleteItemAsync(HOST_KEY);
}
export async function call<T>(path:string,method:Method='GET',payload?:unknown):Promise<T> {
  const base=await getHost();
  if (!base || !(await getCookie())) throw Error('Not connected to Odoo. Sign in from Profile.');
  return http<T>(base,path,method,payload);
}
export const listPlans=()=>call<{ok:boolean;plans:{id:number;name:string;visit_date:string;purpose:string;state:string;total_visits:number}[]}>('/mobile/api/plans');
export type CustomerPage = {ok:boolean;partners:Customer[];has_more:boolean;next_offset:number};
export async function findCustomers(q:string='', offset:number=0, limit:number=50):Promise<CustomerPage> {
  return call<CustomerPage>(`/zencore/field/v3/customers?q=${encodeURIComponent(q.trim())}&offset=${offset}&limit=${limit}`);
}
export type CustomerRecord = {id:number;name:string;phone?:string;street?:string;city?:string;latitude?:number|null;longitude?:number|null};
export type CustomerCreateInput = {name:string;phone:string;email:string;address:string;latitude:number;longitude:number};
export async function createCustomer(data:CustomerCreateInput):Promise<{ok:boolean;customer:CustomerRecord}> {
  return call('/zencore/field/v11/customers/create','POST',data);
}
export type EmployeePage = {ok:boolean;employees:{id:number;name:string}[];has_more:boolean;next_offset:number};
export async function findEmployees(q:string='',offset:number=0,limit:number=50):Promise<EmployeePage> {
 return call<EmployeePage>(`/zencore/field/v4/employees?q=${encodeURIComponent(q.trim())}&offset=${offset}&limit=${limit}`);
}
export const planCustomers=(id:number)=>call<{customers:Customer[];tracker_id:number|null}>(`/mobile/api/plans/${id}/customers`);
export type MobileBridgeHealth = {
  ok:boolean;
  bridge:string;
  api_version:string;
  create_plan:string;
  tracking:string;
};
export const checkMobileBridge = () => call<MobileBridgeHealth>('/zencore/field/v3/health');

export async function submitPlan(p:Plan,submit=true) {
  if(!p.targets.length || p.targets.length>40) throw Error('Add 1 to 40 target lines.');
  if(p.targets.some(t=>!(t.customerIds?.length || t.customerId))) throw Error('Select at least one Odoo customer for every target.');
  await checkMobileBridge();
  return call<{ok:boolean;plan_id:number;plan_name:string;state:string}>('/zencore/field/v3/plans','POST',{
    date:p.date,purpose:p.purpose,priority:p.priority,targets:p.targets,
    transport:p.transport,food:p.food,other:p.other,notes:p.notes,submit,
  });
}
export async function batchGps(points:GpsPointInput[]) {
  if(!points.length)return {ok:true,accepted:[] as string[],rejected:[] as {id:string;reason:string}[]};
  return call<{ok:boolean;accepted:string[];rejected:{id:string;reason:string}[]}>('/zencore/field/v3/gps/batch','POST',{points});
}
export const getTodayTracker=()=>call<{tracker:null|{id:number;is_tracking:boolean;total_distance_km:number;total_visits:number;total_visited:number}}>('/mobile/api/tracker/today');
export const startOdooTracking=(trackerId?:number)=>call<{ok:boolean;error?:string}>('/salesperson_tracking/start','POST',{tracker_id:trackerId});
export const stopOdooTracking=(trackerId?:number)=>call<{ok:boolean;error?:string}>('/salesperson_tracking/stop','POST',{tracker_id:trackerId});
export const checkIn=(body:{partner_id:number;latitude:number;longitude:number;tracker_id:number})=>call<{ok:boolean;checkin_id:number}>('/mobile/api/checkin','POST',body);
export const checkOut=(id:number,body:{latitude:number;longitude:number;notes:string;outcome:string})=>call<{ok:boolean;duration_minutes:number}>(`/mobile/api/checkout/${id}`,'POST',body);
export const pingGps=(p:{latitude:number;longitude:number;accuracy:number;capturedAt:number})=>call<{status:string}>('/salesperson_tracking/mobile/ping','POST',{latitude:p.latitude,longitude:p.longitude,accuracy:p.accuracy,log_time:p.capturedAt,distance:0});

// Plan-specific API: not the legacy /tracker/today endpoint.
export type RemotePlan = {
  id:number; name:string; visit_date:string; state:string;
  purpose:string; salesperson_id:number; salesperson:string;
  total_visits:number; tracker_id:number|null; is_tracking:boolean;
};
export const myVisitPlans = () => call<{ok:boolean;plans:RemotePlan[]}>(
  '/zencore/field/v3/my-plans');
export const startPlanTracking = (planId:number) => call<{
  ok:boolean;plan_id:number;tracker_id:number;state:string;is_tracking:boolean
}>(`/zencore/field/v3/plans/${planId}/start`,'POST',{});
export const stopPlanTracking = (planId:number) => call<{
  ok:boolean;plan_id:number;tracker_id:number;is_tracking:boolean
}>(`/zencore/field/v3/plans/${planId}/stop`,'POST',{});
// Authenticated atomic Odoo-side switch: stop other active trackers, start selected.
export const switchPlanTracking = (planId:number) => call<{
  ok:boolean;plan_id:number;tracker_id:number;state:string;is_tracking:boolean;stopped_plan_ids:number[]
}>(`/zencore/field/v5/plans/${planId}/switch`,'POST',{});

export type RemotePlanDetail = RemotePlan & {
 priority:string; transport:number;food:number;other:number;total_cost:number;notes:string;
 targets:{id:number; expected_time_minutes:number;employee_ids:number[];employee_names:string[];
 customer_ids:number[];customer_names:string[];customer_locations?:{id:number;latitude:number|null;longitude:number|null}[];from_location:string;to_location:string;
 expected_km:number;notes:string}[];
};
export const getPlanDetail=(id:number)=>call<{ok:boolean;plan:RemotePlanDetail}>(`/zencore/field/v4/plans/${id}`);

export type PhotoUploadPayload={id:string;plan_id:number;tracker_id:number|null;customer_id:number|null;file_name:string;mime_type:string;captured_at:number;note:string;content_base64:string;latitude?:number|null;longitude?:number|null;accuracy_m?:number|null;location_name?:string;device_name?:string;photo_origin?:'camera'|'gallery'};
export type PhotoUploadReceipt={ok:boolean;photo_id:string;attachment_id:number;message_id:number;already_uploaded?:boolean};
export const uploadVisitPhoto=(payload:PhotoUploadPayload)=>call<PhotoUploadReceipt>('/zencore/field/v5/photos/upload','POST',payload);

// V18 authenticated dashboard/profile. No credentials are embedded in these requests.
export type FieldProfile={id:number;name:string;login:string;company:string;role:string;reports_to:string};
export type FieldDashboard={visit_plans:number;completed_plans:number;completed_visits?:number;completed_customer_visits:number|null;total_distance_km:number|null};
export const fieldProfile=()=>call<FieldProfile>('/zencore/field/v6/profile');
export const fieldDashboard=()=>call<FieldDashboard>('/zencore/field/v6/dashboard');

// V19 read-only daily schedule. Only Odoo-owned visit plans for the authenticated user.
export type FieldTodayItem={plan_id:number;plan_name:string;line_id:number;customer_names:string[];visited:boolean;location:string;plan_state:string};
export type FieldTodaySummary={date:string;total_targets:number;completed_targets:number;schedule:FieldTodayItem[];next_visit:(FieldTodayItem&{customer_name:string})|null};
export const fieldTodaySummary=()=>call<FieldTodaySummary>('/zencore/field/v7/home/today');

export type ApprovalRequest = {id:number;name:string;owner:string;role:string;visit_date:string;purpose:string;customer_names:string;status:string};
export const getPendingApprovals=()=>call<{ok:boolean;approvals:ApprovalRequest[]}>('/zencore/field/v8/approvals');
export const decideApproval=(id:number,action:'approve'|'reject')=>call<{ok:boolean;state:string;plan_id:number}>(`/zencore/field/v8/approvals/${id}/${action}`,'POST',{});

// Public opt-in self-registration: always provisions the Salesperson role only.
// Password is transmitted to Odoo via HTTPS and is not persisted on the phone.
export type AccountRegistration = {name:string;email:string;phone:string;password:string;confirm_password:string};
export async function registerOdooAccount(host:string,database:string,data:AccountRegistration):Promise<string> {
  const base=hostOrigin(host);
  if(!database.trim())throw Error('Enter the Odoo database name.');
  const result=await http<{ok:boolean;message:string}>(base,'/zencore/field/v10/register','POST',{
    ...data,database:database.trim(),requested_role:'salesman'
  });
  return result.message||'If the account is eligible, sign in with your password.';
}
export function odooPasswordResetUrl(host:string):string {
  return hostOrigin(host)+'/web/reset_password';
}
