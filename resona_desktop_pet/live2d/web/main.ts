let mouseGaze={active:false,x:0,y:0,at:0},mouseGazeWeight=0;
import {StableController} from './stable_controller';
let guard:StableController|null=null,profile:any=null,idlePlaying=false;
import {CubismFramework} from '@framework/live2dcubismframework';
import {CubismUserModel} from '@framework/model/cubismusermodel';
import {CubismMatrix44} from '@framework/math/cubismmatrix44';
import {CubismMotion} from '@framework/motion/cubismmotion';
import {CubismMotionManager} from '@framework/motion/cubismmotionmanager';
import {CubismPhysics} from '@framework/physics/cubismphysics';

const w:any=window, canvas=document.querySelector<HTMLCanvasElement>('#model')!;
const presets:Record<string,Record<string,number>>={
 neutral:{},serious:{},smile:{ParamMouthForm:.55,ParamEyeLOpen:.92,ParamEyeROpen:.92},
 angry:{ParamBrowLY:-.45,ParamBrowRY:-.45,ParamMouthForm:-.35},
 sad:{ParamBrowLY:-.3,ParamBrowRY:-.3,ParamEyeLOpen:.78,ParamEyeROpen:.78,ParamMouthForm:-.4},
 thinking:{ParamAngleZ:3,ParamEyeBallX:.2,ParamEyeBallY:.2,ParamBrowLY:.2},
 surprised:{ParamBrowLY:.65,ParamBrowRY:.65,ParamMouthOpenY:.16},
 dislike:{ParamEyeLOpen:.72,ParamEyeROpen:.72,ParamMouthForm:-.3},
 smirk:{ParamMouthForm:.7,ParamEyeLOpen:.8,ParamEyeROpen:.9,ParamBrowLY:.15},
 embarrassed:{ParamEyeBallY:-.2,ParamMouthForm:-.15,ParamBrowLY:.2},
 shy:{ParamEyeBallY:-.3,ParamMouthForm:.35,ParamAngleZ:-2},
 worry:{ParamBrowLY:.2,ParamBrowRY:.2,ParamEyeLOpen:.85,ParamEyeROpen:.85,ParamMouthForm:-.2}
};
const looks:Record<string,number[]>={center:[0,0],left:[-.55,0],right:[.55,0],up:[0,.4],down:[0,-.4]};
let bridge:any,user:CubismUserModel,gl:WebGLRenderingContext,physics:CubismPhysics|null=null;
let parameters:any[]=[],motions:Record<string,CubismMotion>={},manager=new CubismMotionManager();
let modelOpacity=1;
let ready=false,baseEmotion='neutral',state='idle',action:any=null,lastAction:any=null,revision=0;
let lastTime=performance.now(),elapsed=0,lastReport=0,mouth=0,audioValue=0,audioAt=0,speaking=false;
let nextBlink=2.8,blinkStart=-10,expressionValues:Record<string,number>={},gaze=[0,0];
let bounds={x:0,y:0,width:1,height:1},pending:any[]=[],motionIntensity=1;
let motionOffsets:Record<string,number>={};
const capabilities={expressions:Object.keys(presets),motions:['none','nod','shake','blink'],looks:Object.keys(looks),unsupported:['wave','raise_arms','hug']};
function report(){
 const m=user?.getModel();
 return {ok:ready,ready,revision,state,speaking,capabilities,opacity:modelOpacity,action:action?{...action,status:'running'}:lastAction,
  parameters:ready?Object.fromEntries(parameters.map(p=>[p.id,m!.getParameterValueByIndex(p.index)])):{},
  mouse_gaze:{active:mouseGaze.active&&performance.now()-mouseGaze.at<350,weight:mouseGazeWeight,x:mouseGaze.x,y:mouseGaze.y},
  idle:{motion:motions.haircheck?'HairCheck':null,playing:idlePlaying&&!action,period_seconds:motions.haircheck?20:null},profile:profile?.version||null,
  model:ready?{parameters:parameters.length,drawables:m!.getDrawableCount()}:null};
}
function command(c:any){
 try {
  if(!ready)throw Error('Renderer not ready');
  if(c.type==='status'){pending.push({id:c.id,status:'observed'});return;}
  if(c.type==='audio'){audioValue=Math.max(0,Math.min(1,Number(c.payload.level)||0));audioAt=performance.now();speaking=!!c.payload.playing;if(!speaking)audioValue=0;return;}
  if(c.type==='mouse_gaze'){
   const p=c.payload;
   if(typeof p.active!=='boolean'||(p.active&&(!Number.isFinite(p.x)||!Number.isFinite(p.y))))throw Error('Invalid mouse gaze');
   mouseGaze={active:p.active,x:p.active?Math.max(-1,Math.min(1,p.x)):mouseGaze.x,y:p.active?Math.max(-1,Math.min(1,p.y)):mouseGaze.y,at:performance.now()};return;
  }
  if(c.type==='opacity'){const v=c.payload.value;if(!Number.isFinite(v)||v<0||v>1)throw Error('Invalid opacity');modelOpacity=v;canvas.style.opacity=String(v);return;}
  if(c.type==='state'){state=c.payload.state;return;}
  if(c.type==='emotion'){baseEmotion=c.payload.emotion in presets?c.payload.emotion:'neutral';return;}
  if(!['perform','reset'].includes(c.type))throw Error('Unknown command');
  if(action)lastAction={...action,status:'cancelled'};
  manager.stopAllMotions();action=null;idlePlaying=false;
  if(c.type==='reset'){baseEmotion='neutral';state='idle';}
  else {
   const p=c.payload;
   if(!(p.expression in presets)||!(p.look in looks)||!capabilities.motions.includes(p.motion)||!Number.isFinite(p.intensity)||p.intensity<0||p.intensity>1||!Number.isInteger(p.hold_ms)||p.hold_ms<300||p.hold_ms>8000)throw Error('Invalid semantic command');
   action={id:c.id,...p,started_at:elapsed,ends_at:elapsed+Math.max(p.hold_ms/1000,p.motion==='blink'?1.2:p.motion==='none'?0:2)};
   if(p.motion!=='none'){motionIntensity=p.intensity;manager.startMotionPriority(motions[p.motion],false,3);}
  }
  revision++;pending.push({id:c.id,status:'started'});
 }catch(e){bridge?.ack(JSON.stringify({id:c.id,ok:false,error:String(e)}));}
}
async function buffer(url:string){const r=await fetch(url);if(!r.ok)throw Error(`${r.status} ${url}`);return r.arrayBuffer();}
function frame(now:number){
 try{
  const dt=Math.min(.05,Math.max(0,(now-lastTime)/1000));lastTime=now;elapsed+=dt;
  const m=user.getModel();
  for(const p of parameters)m.setParameterValueByIndex(p.index,p.default);
  const set=(id:string,v:number)=>{const p=parameters.find(p=>p.id===id);if(p)m.setParameterValueByIndex(p.index,Math.max(p.min,Math.min(p.max,v)));};
  const get=(id:string)=>{const p=parameters.find(p=>p.id===id);return p?m.getParameterValueByIndex(p.index):0;};
  set('ParamBreath',.35-.3*Math.cos(elapsed*1.25));set('ParamAngleZ',.65*Math.sin(elapsed*.65));
  set('ParamBodyAngleX',1.3*Math.sin(elapsed*.6));set('ParamShoulderY',.12*Math.sin(elapsed*1.25));
  // Semantic gestures own the motion manager until their hold expires.
  // Returning to the reference loop is smoothed by motionOffsets and guard.
  if(!action&&manager.isFinished()&&motions.haircheck){
   motionIntensity=1;manager.startMotionPriority(motions.haircheck,false,2);idlePlaying=true;
  }
  const before=parameters.map(p=>m.getParameterValueByIndex(p.index));
  if(!manager.isFinished())manager.updateMotion(m,dt);
  for(const p of parameters){
   const weight=action?.motion==='blink'&&motionIntensity>0&&p.id.match(/^ParamEye[LR]Open$/)?1:motionIntensity;
   const target=(get(p.id)-before[p.index])*weight;
   if(p.id.startsWith('ParamAngle')||p.id.startsWith('ParamBody')){
    motionOffsets[p.id]=(motionOffsets[p.id]||0)+(target-(motionOffsets[p.id]||0))*(1-Math.exp(-dt/.08));
    set(p.id,before[p.index]+motionOffsets[p.id]);
   }else set(p.id,before[p.index]+target);
  }
  if(action&&elapsed>=action.ends_at){lastAction={...action,status:'completed'};action=null;revision++;}
  if(elapsed>=nextBlink){blinkStart=elapsed;nextBlink=elapsed+2.8+Math.random()*2.8;}
  const b=elapsed-blinkStart, blink=b<.09?1-b/.09:b<.13?0:b<.25?(b-.13)/.12:1;
  const expression=action?.expression||(state==='thinking'?'thinking':baseEmotion);
  const intensity=action?.intensity??.65, preset=presets[expression]||{};
  const smoothing=1-Math.exp(-dt/0.18);
  for(const p of parameters){
   const eye=p.id==='ParamEyeLOpen'||p.id==='ParamEyeROpen';
   const target=p.id in preset?(eye?1+(preset[p.id]-1)*intensity:preset[p.id]*intensity):(eye?1:0);
   expressionValues[p.id]=(expressionValues[p.id]??(eye?1:0))+(target-(expressionValues[p.id]??(eye?1:0)))*smoothing;
   if(eye)set(p.id,get(p.id)*blink*expressionValues[p.id]);
   else if(p.id==='ParamMouthForm'||p.id==='ParamMouthOpenY'||p.id.startsWith('ParamBrow'))set(p.id,p.default+expressionValues[p.id]);
   else if(p.id==='ParamAngleZ'||p.id==='ParamEyeBallX'||p.id==='ParamEyeBallY')set(p.id,get(p.id)+expressionValues[p.id]);
  }
  const gazeTarget=looks[action?.look||'center'];
  for(let i=0;i<2;i++)gaze[i]+=(gazeTarget[i]*intensity-gaze[i])*smoothing;
  set('ParamEyeBallX',get('ParamEyeBallX')+gaze[0]);set('ParamEyeBallY',get('ParamEyeBallY')+gaze[1]);
  set('ParamAngleX',get('ParamAngleX')+gaze[0]*9);set('ParamAngleY',get('ParamAngleY')+gaze[1]*7);
  const manualActive=mouseGaze.active&&now-mouseGaze.at<350;
  mouseGazeWeight+=((manualActive?1:0)-mouseGazeWeight)*(1-Math.exp(-dt/(manualActive ? .12 : .25)));
  // Manual aim overrides only eyes/head. Motion time, expression, breath and
  // physics keep running, so release blends back without cancelling actions.
  for(const [id,target]of Object.entries({ParamEyeBallX:mouseGaze.x*.65,ParamEyeBallY:mouseGaze.y*.4,
                                        ParamAngleX:mouseGaze.x*16,ParamAngleY:mouseGaze.y*10,ParamAngleZ:0})){
   set(id,get(id)*(1-mouseGazeWeight)+target*mouseGazeWeight);
  }
  if(guard){
   const requested=Object.fromEntries(parameters.map(p=>[p.id,get(p.id)]));
   const inputs=parameters.map(p=>p.id).filter(id=>!profile.physicsOutputs.includes(id)&&id!=='ParamMouthOpenY');
   const safe=guard.step(requested,dt,inputs);for(const [id,v]of Object.entries(safe))set(id,v);
  }
  physics?.evaluate(m,dt);
  if(guard){
   const physical=guard.step(Object.fromEntries(parameters.map(p=>[p.id,get(p.id)])),dt,profile.physicsOutputs);
   for(const [id,v]of Object.entries(physical))set(id,v);
  }
  const targetMouth=speaking&&now-audioAt<250?audioValue:0;
  mouth+=(targetMouth-mouth)*(1-Math.exp(-dt/(targetMouth > mouth ? .035 : .075)));
  if(speaking)set('ParamMouthOpenY',mouth);else if(mouth>.002)set('ParamMouthOpenY',Math.max(get('ParamMouthOpenY'),mouth));
  if(guard){const safeMouth=guard.step({ParamMouthOpenY:get('ParamMouthOpenY')},dt,['ParamMouthOpenY']);set('ParamMouthOpenY',safeMouth.ParamMouthOpenY);}
  m.update();
  const ratio=Math.min(devicePixelRatio,2),width=Math.max(1,Math.round(canvas.clientWidth*ratio)),height=Math.max(1,Math.round(canvas.clientHeight*ratio));
  if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;}
  let fitWidth=bounds.width*1.08,fitHeight=bounds.height*1.04;
  if(fitWidth/fitHeight>width/height)fitHeight=fitWidth*height/width;else fitWidth=fitHeight*width/height;
  const sx=2/fitWidth,sy=2/fitHeight,mat=new CubismMatrix44();
  mat.setMatrix(new Float32Array([sx,0,0,0,0,sy,0,0,0,0,1,0,-bounds.x*sx,-bounds.y*sy,0,1]));
  const r=user.getRenderer();r.setMvpMatrix(mat);gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
  r.setRenderState(null,[0,0,width,height]);r.drawModel();
  if(gl.getError()!==gl.NO_ERROR)throw Error('WebGL draw error');
  w.live2dSnapshot=report();
  for(const result of pending.splice(0))bridge?.ack(JSON.stringify({...result,...w.live2dSnapshot,ok:true}));
  if(now-lastReport>250){lastReport=now;bridge?.report(JSON.stringify(w.live2dSnapshot));}
  requestAnimationFrame(frame);
 }catch(e){fail(e);}
}
function fail(e:any){ready=false;document.querySelector('#error')!.textContent='Live2D: '+String(e);bridge?.report(JSON.stringify({ready:false,ok:false,error:String(e)}));}
async function main(){
 if(w.qt)await new Promise<void>(resolve=>new w.QWebChannel(w.qt.webChannelTransport,(channel:any)=>{bridge=channel.objects.petBridge;bridge.command.connect((s:string)=>command(JSON.parse(s)));resolve();}));
 gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:true,preserveDrawingBuffer:true})!;
 if(!gl)throw Error('WebGL unavailable');
 if(!CubismFramework.startUp())throw Error('Cubism startup failed');CubismFramework.initialize();
 const modelUrl=new URL('../model/'+(new URLSearchParams(location.search).get('model')||'setsuna_psd2live_v001.model3.json'),location.href);
 const settings=JSON.parse(new TextDecoder().decode(await buffer(modelUrl.href)));
 const resource=(file:string)=>new URL(file,modelUrl).href;
 user=new CubismUserModel();user.loadModel(await buffer(resource(settings.FileReferences.Moc)),true);
 const m=user.getModel();
 for(let i=0;i<m.getParameterCount();i++)parameters.push({index:i,id:m.getParameterId(i).getString(),default:m.getParameterDefaultValue(i),min:m.getParameterMinimumValue(i),max:m.getParameterMaximumValue(i)});
 if(settings.FileReferences.Motions.HairCheck){
  profile=JSON.parse(new TextDecoder().decode(await buffer(resource('working-range.json'))));
  guard=new StableController(profile.ranges,parameters);
 }
 m.update();let xmin=Infinity,xmax=-Infinity,ymin=Infinity,ymax=-Infinity;
 for(let i=0;i<m.getDrawableCount();i++){if(m.getDrawableOpacity(i)<.01)continue;const points=m.getDrawableVertices(i);for(let j=0;j<points.length;j+=2){xmin=Math.min(xmin,points[j]);xmax=Math.max(xmax,points[j]);ymin=Math.min(ymin,points[j+1]);ymax=Math.max(ymax,points[j+1]);}}
 bounds={x:(xmin+xmax)/2,y:(ymin+ymax)/2,width:xmax-xmin,height:ymax-ymin};
 if(!Number.isFinite(bounds.width)||bounds.width<=0)throw Error('Invalid model bounds');
 user.createRenderer();const renderer=user.getRenderer();renderer.startUp(gl);renderer.setIsPremultipliedAlpha(true);
 for(let i=0;i<settings.FileReferences.Textures.length;i++){
  const im=new Image();im.src=resource(settings.FileReferences.Textures[i]);await im.decode();const tex=gl.createTexture()!;
  gl.bindTexture(gl.TEXTURE_2D,tex);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,true);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,im);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);renderer.bindTexture(i,tex);
 }
 renderer.loadShaders(new URL('vendor/Framework/Shaders/WebGL/',location.href).href);
 for(const [key,group] of Object.entries({nod:'Nod',shake:'Shake',blink:'Blink',haircheck:'HairCheck'})){
  if(group==='HairCheck'&&!settings.FileReferences.Motions[group])continue;
  const data=await buffer(resource(settings.FileReferences.Motions[group][0].File));
  motions[key]=CubismMotion.create(data,data.byteLength);motions[key].setEffectIds([],[]);motions[key].setFadeInTime(.18);motions[key].setFadeOutTime(.25);
 }
 if(settings.FileReferences.Physics){const data=await buffer(resource(settings.FileReferences.Physics));physics=CubismPhysics.create(data,data.byteLength);}
 if(motions.haircheck)motions.haircheck.setLoop(true);
 ready=true;w.live2d={command,snapshot:report};bridge?.report(JSON.stringify(report()));lastTime=performance.now();requestAnimationFrame(frame);
}
canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();fail('WebGL context lost; reload required');});
main().catch(fail);
