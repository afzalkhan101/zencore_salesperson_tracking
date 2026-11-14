import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import {Platform} from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import {addVisitPhoto,getVisitPhotos,pendingVisitPhotos,markPhotoUploaded,setPhotoError,removePendingPhoto,type VisitPhoto} from './storage';
import {uploadVisitPhoto} from './odoo';
const LIMIT_BYTES=5*1024*1024;
const uuid=()=>`${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
let uploadInFlight:Promise<number>|null=null;
export {getVisitPhotos};
export type {VisitPhoto} from './storage';
export async function chooseAndQueuePhoto(planId:number,trackerId:number|null,customerId:number|null,note:string,camera:boolean):Promise<VisitPhoto|null>{
 const grant=camera?await ImagePicker.requestCameraPermissionsAsync():await ImagePicker.requestMediaLibraryPermissionsAsync();
 if(!grant.granted)throw Error('Camera or photo library permission required.');
 const picked=camera
 ?await ImagePicker.launchCameraAsync({mediaTypes:['images'],quality:.65,allowsEditing:false})
 :await ImagePicker.launchImageLibraryAsync({mediaTypes:['images'],quality:.65,allowsMultipleSelection:false});
 if(picked.canceled||!picked.assets.length)return null;
 const asset=picked.assets[0];
 // Convert to JPEG on supported devices via picker quality; reject unsupported types.
 const mime=(asset.mimeType||'image/jpeg').toLowerCase();
 if(!['image/jpeg','image/png','image/webp'].includes(mime))throw Error('Only JPEG, PNG and WEBP images are allowed.');
 const id=uuid(); const ext=mime==='image/png'?'png':mime==='image/webp'?'webp':'jpg';
 const directory=FileSystem.documentDirectory+'zencore_visit_evidence/';
 await FileSystem.makeDirectoryAsync(directory,{intermediates:true});
 const fileUri=directory+id+'.'+ext;
 await FileSystem.copyAsync({from:asset.uri,to:fileUri});
 const info=await FileSystem.getInfoAsync(fileUri);
 if(!info.exists||!info.size||info.size>LIMIT_BYTES){await FileSystem.deleteAsync(fileUri,{idempotent:true});throw Error('Photo is empty or larger than 5 MB. Retake at lower resolution.');}
 // Capture-location is only applied to newly TAKEN photos. Gallery images may be
 // historical and must never be assigned the uploader's current position.
 let latitude:number|null=null,longitude:number|null=null,accuracyM:number|null=null,locationName='';
 if(camera){
  try{
   let permission=await Location.getForegroundPermissionsAsync();
   if(!permission.granted && permission.canAskAgain){
    permission=await Location.requestForegroundPermissionsAsync();
   }
   if(permission.granted){
    const fix=await Promise.race([
     Location.getCurrentPositionAsync({accuracy:Location.Accuracy.Balanced}),
     new Promise<never>((_,reject)=>setTimeout(()=>reject(Error('Location timeout')),6000)),
    ]);
    if(fix.coords.accuracy!=null && fix.coords.accuracy<=150 && Number.isFinite(fix.coords.latitude)&&Number.isFinite(fix.coords.longitude)){
     latitude=fix.coords.latitude;longitude=fix.coords.longitude;accuracyM=fix.coords.accuracy;
     try{
      const results=await Promise.race([
       Location.reverseGeocodeAsync({latitude,longitude}),
       new Promise<never>((_,reject)=>setTimeout(()=>reject(Error('Geocode timeout')),4500)),
      ]);
      const address=results[0];
      if(address)locationName=[address.name,address.street,address.district,address.subregion,address.city,address.region,address.country].filter((v,i,a)=>Boolean(v)&&a.indexOf(v)===i).join(', ').slice(0,240);
     }catch{/* Keep truthful GPS coordinates when reverse geocoding is offline. */}
    }
   }
  }catch{/* Photo evidence is still queued; location stays unavailable. */}
 }
 const model=(Platform.constants as {Model?:string}).Model;
 const photo:VisitPhoto={id,planId,trackerId,customerId,fileUri,fileName:`visit_${planId}_${id}.${ext}`,mimeType:mime,size:info.size,capturedAt:Date.now(),note:note.slice(0,1500),status:'pending',attachmentId:null,messageId:null,error:'',latitude,longitude,accuracyM,locationName,deviceName:model||Platform.OS,photoOrigin:camera?'camera':'gallery'};
 try {await addVisitPhoto(photo);}catch(e){await FileSystem.deleteAsync(fileUri,{idempotent:true});throw e;}
 return photo;
}
export async function deleteQueuedPhoto(photo:VisitPhoto){
 if(photo.status!=='pending')throw Error('Already uploaded. Remove the attachment from Odoo with appropriate permissions.');
 await removePendingPhoto(photo.id);
 await FileSystem.deleteAsync(photo.fileUri,{idempotent:true});
}
async function sendBatch(maxItems:number):Promise<number>{
 const items=await pendingVisitPhotos(maxItems);let uploaded=0;
 for(const p of items){
  try {
   const info=await FileSystem.getInfoAsync(p.fileUri);
   if(!info.exists||!info.size||info.size>LIMIT_BYTES){await setPhotoError(p.id,'Local photo unavailable or exceeds 5 MB');continue;}
   const base64=await FileSystem.readAsStringAsync(p.fileUri,{encoding:FileSystem.EncodingType.Base64});
   const answer=await uploadVisitPhoto({id:p.id,plan_id:p.planId,tracker_id:p.trackerId,customer_id:p.customerId,file_name:p.fileName,mime_type:p.mimeType,captured_at:p.capturedAt,note:p.note,content_base64:base64,latitude:p.latitude??null,longitude:p.longitude??null,accuracy_m:p.accuracyM??null,location_name:p.locationName||'',device_name:p.deviceName||'',photo_origin:p.photoOrigin||'camera'});
   if(!answer.ok||!answer.attachment_id||!answer.message_id)throw Error('Odoo photo acknowledgement is missing.');
   await markPhotoUploaded(p.id,answer.attachment_id,answer.message_id);
   uploaded++;
   // File intentionally retained for offline preview; remove only via explicit cleanup policy.
  }catch(e){await setPhotoError(p.id,e instanceof Error?e.message:String(e));if(/session expired|not connected|network|timeout|fetch/i.test(String(e)))break;}
 }
 return uploaded;
}
export function flushPhotos(maxItems=3):Promise<number>{
 if(!uploadInFlight)uploadInFlight=sendBatch(maxItems).finally(()=>{uploadInFlight=null;});
 return uploadInFlight;
}
