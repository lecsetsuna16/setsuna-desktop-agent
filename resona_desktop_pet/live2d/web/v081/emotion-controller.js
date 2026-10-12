// Cubism expression controller. Rebuild the base pose before each update.
import {createAngryEyeTransition} from './angry-eye-transition.js';
export function createEmotionController({model,contract,manager,motions,onChange=()=>{}}) {
 const entries=new Map(contract.expressions.map(e=>[e.name,e]));
 const handover=contract.angryEyeTransition?createAngryEyeTransition(contract.angryEyeTransition):null;
 const eyeIndices=handover?Object.fromEntries(Array.from({length:model.getParameterCount()},(_,i)=>[model.getParameterId(i).getString(),i])):null;
 const read=id=>model.getParameterValueByIndex(eyeIndices[id]);
 const write=(id,v)=>model.setParameterValueByIndex(eyeIndices[id],v);
 if(handover)for(const id of ['ParamAngryFocus','ParamEyeLOpen','ParamEyeROpen'])if(!Number.isInteger(eyeIndices[id]))throw Error('Missing eye handover parameter '+id);
 let current='neutral',rest=0,target=0;
 function setEmotion(tag){
  if(typeof tag!=='string')return {accepted:false,reason:'invalid-emotion'};
  const name=/^<E:([a-z_]+)>$/.exec(tag)?.[1]??tag;
  if(!entries.has(name))return {accepted:false,reason:'unknown-emotion',tag};
  if(name===current&&started)return {accepted:true,name,restarted:false};
  const previous=current;
  handover?.request({previous,name,fromFocus:read('ParamAngryFocus'),toFocus:entries.get(name).parameters?.ParamAngryFocus??0});
  current=name;target=entries.get(name).restMouthOpen;manager.startMotion(motions.get(name),false);started=true;onChange({previous,name});
  return {accepted:true,name,restarted:true};
 }
 let started=false;setEmotion('neutral');
 return {setEmotion,reset:()=>setEmotion('neutral'),update(dt){
  rest+=(target-rest)*(1-Math.exp(-dt/0.10));manager.updateMotion(model,dt);
  if(handover){const pose=handover.apply(dt,{focus:read('ParamAngryFocus'),left:read('ParamEyeLOpen'),right:read('ParamEyeROpen')});if(pose){write('ParamAngryFocus',pose.focus);write('ParamEyeLOpen',pose.left);write('ParamEyeROpen',pose.right)}}
 },get eyeTransitionState(){return handover?.state??null},get restMouthOpen(){return rest},get name(){return current},get entry(){return entries.get(current)}};
}
