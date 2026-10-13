import {CubismFramework} from '@framework/live2dcubismframework';
import {CubismUserModel} from '@framework/model/cubismusermodel';
import {CubismMatrix44} from '@framework/math/cubismmatrix44';
import {CubismMotion} from '@framework/motion/cubismmotion';
import {CubismMotionManager} from '@framework/motion/cubismmotionmanager';
import {CubismExpressionMotion} from '@framework/motion/cubismexpressionmotion';
import {CubismExpressionMotionManager} from '@framework/motion/cubismexpressionmotionmanager';
import {createEmotionController} from './emotion-controller.js';
import {createThoughtController} from './thought-controller.js';
import {createFrameDriver} from './frame-driver.js';
import {createFrameLimiter} from './frame-limiter.js';
import {createSingingController} from './singing-controller.js';

class PetModel extends CubismUserModel {
  physics(dt:number, reset:boolean) {
    if (!this._physics) return;
    if (reset) this._physics.stabilization(this.getModel());
    this._physics.evaluate(this.getModel(), dt);
  }
}
const w:any=window, canvas=document.querySelector<HTMLCanvasElement>('#model')!;
const query=new URLSearchParams(location.search);
const frameLimit=createFrameLimiter(Number(query.get('fps')),Number(query.get('hidden_fps')));
let renderVisible=true, renderedFrames=0;
let animationHandle:number|null=null, timerHandle:any=null;
const looks:Record<string,number[]>={center:[0,0],left:[-.55,0],right:[.55,0],up:[0,.4],down:[0,-.4]};
let user:PetModel, gl:WebGLRenderingContext, bridge:any, emotion:any, thought:any, singer:any, advance:any;
let params:any[]=[], contract:any, bounds:any, physicsOutputs:string[]=[], resetPhysics=true;
const paramById=new Map<string,any>();
let ready=false, baseEmotion='neutral', state='idle', ordinaryTime=0, revision=0, opacity=1;
let replySelected=false, singReplyBound=false, musicActive=false;
let action:any=null, lastAction:any=null, pending:any[]=[], singPose:Record<string,number>={};
let last=performance.now(), lastReport=0, audioAt=0, audioLevel=0, speaking=false, mouth=0;
let manual={active:false,x:0,y:0,at:0}, manualWeight=0, gestureWeight=0, gestureTarget=[0,0];
let capabilities:any={expressions:[], motions:['none','nod','shake','blink'], looks:Object.keys(looks), actions:['sing'], unsupported:['head_pat','cheek_poke','hug','shoulder_pat','wave']};
const get=(id:string)=>{const p=paramById.get(id);return p?user.getModel().getParameterValueByIndex(p.index):0};
const set=(id:string,v:number)=>{const p=paramById.get(id);if(p)user.getModel().setParameterValueByIndex(p.index,Math.max(p.min,Math.min(p.max,v)))};
const capture=()=>Object.fromEntries(params.map(p=>[p.id,get(p.id)]));
const busy=()=>singer&&singer.state!=='idle';
function report(){return {
  ok:ready, ready, revision, state, speaking, opacity, profile:contract?.version, capabilities,
  rendering:{fps_limit:frameLimit.fps,hidden_fps:frameLimit.hiddenFps,visible:renderVisible&&!document.hidden,frames:renderedFrames},
  expression:emotion?.name, expression_owner:replySelected?"reply":state==='thinking'?"thinking":"base", action:action?{...action,status:'running'}:lastAction,
  singing:singer?{...singer.status,active:busy(),music_bound:musicActive,reply_bound:singReplyBound,audio_provided:false,queue_policy:'reject'}:null,
  thought:thought?.state, eye_transition:emotion?.eyeTransitionState,
  mouse_gaze:{active:!busy()&&manual.active&&performance.now()-manual.at<350,weight:manualWeight,x:manual.x,y:manual.y},
  idle:{motion:'gentle',playing:!busy()&&!action}, parameters:ready?capture():{},
  model:ready?{parameters:params.length,drawables:user.getModel().getDrawableCount()}:null
};}
function command(c:any){
  try {
    if(!ready)throw Error('Renderer not ready');
    const p=c.payload||{};
    if(c.type==='visibility'){renderVisible=p.visible!==false;scheduleFrame();return;}
    if(c.type==='status'){pending.push({id:c.id,status:'observed'});return;}
    if(c.type==='opacity'){
      if(!Number.isFinite(p.value)||p.value<0||p.value>1)throw Error('Invalid opacity');
      opacity=p.value;canvas.style.opacity=String(opacity);return;
    }
    if(c.type==='music_state'){
      musicActive=!!p.playing;singReplyBound=false;
      if(!musicActive)singer.stop();
      return;
    }
    if(c.type==='audio'){audioLevel=Math.max(0,Math.min(1,Number(p.level)||0));speaking=!!p.playing;audioAt=performance.now();return;}
    if(c.type==='state'){
      state=p.state;
      if(state==='thinking'){
        replySelected=false;
        if(action){lastAction={...action,status:'cancelled'};action=null;}
      }
      if(state==='idle'&&singReplyBound){singer.stop();singReplyBound=false;}
      return;
    }
    if(c.type==='emotion'){
      if(!capabilities.expressions.includes(p.emotion))throw Error('Unknown expression');
      baseEmotion=p.emotion;return;
    }
    if(c.type==='mouse_gaze'){
      if(typeof p.active!=='boolean'||p.active&&(!Number.isFinite(p.x)||!Number.isFinite(p.y)))throw Error('Invalid mouse gaze');
      manual={active:p.active,x:p.active?Math.max(-1,Math.min(1,p.x)):manual.x,y:p.active?Math.max(-1,Math.min(1,p.y)):manual.y,at:performance.now()};return;
    }
    if(c.type==='sing'){
      if(!['start','stop'].includes(p.command))throw Error('Singing command must be start or stop');
      if(p.command==='start'){
        if(busy())throw Error('Singing is already active; request rejected, not queued');
        const duration=p.duration_seconds??16;
        if(!Number.isFinite(duration)||duration<1||duration>300)throw Error('Singing duration must be 1..300 seconds');
        singReplyBound=p.reply_bound===true;
        singPose=capture();singer.start(singReplyBound?300:duration);
      }else {singer.stop();singReplyBound=false;}
      revision++;pending.push({id:c.id,status:p.command==='start'?'started':'stopping'});return;
    }
    if(c.type==='reset'){
      if(action)lastAction={...action,status:'cancelled'};
      action=null;baseEmotion='neutral';state='idle';replySelected=false;singReplyBound=false;singer.stop();
      revision++;pending.push({id:c.id,status:busy()?'stopping':'started'});return;
    }
    if(c.type!=='perform')throw Error('Unknown command');
    if(busy())throw Error('Singing owns the model; stop singing before another action');
    if(!capabilities.expressions.includes(p.expression)||!capabilities.motions.includes(p.motion)||!(p.look in looks)||
        !Number.isFinite(p.intensity)||p.intensity<0||p.intensity>1||!Number.isInteger(p.hold_ms)||p.hold_ms<300||p.hold_ms>8000)throw Error('Invalid semantic command');
    if(action)lastAction={...action,status:'cancelled'};
    action={id:c.id,...p,started_at:ordinaryTime,ends_at:ordinaryTime+Math.max(p.hold_ms/1000,p.motion==='none'?0:2)};
    baseEmotion=p.expression;replySelected=true;
    revision++;pending.push({id:c.id,status:'started'});
  }catch(e){bridge?.ack(JSON.stringify({id:c.id,ok:false,error:String(e),ready}));}
}
function updateMotion(dt:number){
  if(musicActive&&!busy()){singPose=capture();singer.start(300);}
  if(busy()){
    // Keep the ordinary expression/gesture clocks paused. The singing controller
    // exclusively owns its authored parameters, including mouth and gaze.
    for(const [id,v] of Object.entries(singPose))set(id,v);
    singer.update(dt,musicActive);return;
  }
  ordinaryTime+=dt;
  if(action&&ordinaryTime>=action.ends_at){lastAction={...action,status:'completed'};action=null;revision++;}
  const t=ordinaryTime, smoothing=1-Math.exp(-dt/.16);
  set('ParamBreath',.35-.3*Math.cos(t*1.25));set('ParamShoulderY',.12*Math.sin(t*1.25));
  set('ParamAngleX',3*Math.sin(t*.55));set('ParamAngleY',1.8*Math.sin(t*.41));set('ParamAngleZ',.65*Math.sin(t*.65));
  set('ParamBodyAngleX',1.3*Math.sin(t*.6));
  const b=Math.abs((t%4.2)-3.9), blink=Math.min(1,b/.13);
  set('ParamEyeLOpen',blink);set('ParamEyeROpen',blink);
  gestureWeight+=((action?.intensity??0)-gestureWeight)*smoothing;
  const target=looks[action?.look||'center'];
  for(let i=0;i<2;i++)gestureTarget[i]+=(target[i]-gestureTarget[i])*smoothing;
  set('ParamEyeBallX',gestureTarget[0]*gestureWeight);set('ParamEyeBallY',gestureTarget[1]*gestureWeight);
  set('ParamAngleX',get('ParamAngleX')+gestureTarget[0]*9*gestureWeight);
  set('ParamAngleY',get('ParamAngleY')+gestureTarget[1]*7*gestureWeight);
  if(action){
    const a=Math.min(2, t-action.started_at), envelope=Math.sin(Math.PI*a/2)**2;
    if(action.motion==='nod')set('ParamAngleY',get('ParamAngleY')+10*Math.sin(a*Math.PI*2)*envelope*action.intensity);
    if(action.motion==='shake')set('ParamAngleX',get('ParamAngleX')+16*Math.sin(a*Math.PI*2)*envelope*action.intensity);
    if(action.motion==='blink'&&a<.3){const lid=Math.min(1,Math.abs(a-.15)/.1);set('ParamEyeLOpen',lid);set('ParamEyeROpen',lid);}
  }
  const manualActive=manual.active&&performance.now()-manual.at<350;
  manualWeight+=((manualActive?1:0)-manualWeight)*(1-Math.exp(-dt/(manualActive ? .12 : .25)));
  for(const [id,v]of Object.entries({ParamEyeBallX:manual.x*.65,ParamEyeBallY:manual.y*.4,ParamAngleX:manual.x*16,ParamAngleY:manual.y*10,ParamAngleZ:0}))set(id,get(id)*(1-manualWeight)+v*manualWeight);
  // Gesture expiry must never expire the reply's expression.
  const name=state==='thinking'&&!replySelected?'thinking':baseEmotion;
  emotion.setEmotion(name);
  // The model's native gaze motion returns to center after 4.8 seconds.
  // Repeat only while the host is waiting for LLM/TTS; an ordinary thinking
  // expression still plays once, and response playback fades it out normally.
  if(state==='thinking'&&!replySelected&&thought&&!thought.state.running)thought.start();
  thought?.update(dt);
  // Keep the supplied expression controller AFTER all head/gaze/blink writers.
  // Angry/crying Multiply=0 head locks and closed-eye material handover depend on it.
  emotion.update(dt);
  const targetMouth=speaking?(performance.now()-audioAt<250?audioLevel:0):emotion.restMouthOpen;
  mouth+=(targetMouth-mouth)*(1-Math.exp(-dt/(speaking ? .045 : .10)));
  set('ParamMouthOpenY',mouth);
}
async function buffer(url:string){const r=await fetch(url);if(!r.ok)throw Error(`${r.status} ${url}`);return r.arrayBuffer();}
function fail(e:any){ready=false;document.querySelector('#error')!.textContent='Live2D: '+String(e);bridge?.report(JSON.stringify({ok:false,ready:false,error:String(e)}));}
function scheduleFrame(){
  if(!ready)return;
  if(animationHandle!==null){cancelAnimationFrame(animationHandle);animationHandle=null;}
  if(timerHandle!==null){clearTimeout(timerHandle);timerHandle=null;}
  if(renderVisible&&!document.hidden)animationHandle=requestAnimationFrame(frame);
  else timerHandle=setTimeout(()=>frame(performance.now()),1000/frameLimit.hiddenFps);
}
function frame(now:number){
  try{
    if(!frameLimit.due(now,renderVisible&&!document.hidden)){scheduleFrame();return;}
    advance(Math.max(0,(now-last)/1000));last=now;
    const m=user.getModel();m.update();
    const ratio=Math.min(devicePixelRatio,2),width=Math.max(1,Math.round(canvas.clientWidth*ratio)),height=Math.max(1,Math.round(canvas.clientHeight*ratio));
    if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;}
    let fw=bounds.width*1.12,fh=bounds.height*1.06;
    if(fw/fh>width/height)fh=fw*height/width;else fw=fh*width/height;
    const sx=2/fw,sy=2/fh,mat=new CubismMatrix44();
    mat.setMatrix(new Float32Array([sx,0,0,0,0,sy,0,0,0,0,1,0,-bounds.x*sx,-bounds.y*sy,0,1]));
    const renderer=user.getRenderer();renderer.setMvpMatrix(mat);
    gl.viewport(0,0,width,height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
    renderer.setRenderState(null,[0,0,width,height]);renderer.drawModel();
    renderedFrames++;
    if(gl.getError()!==gl.NO_ERROR)throw Error('WebGL draw error');
    w.live2dSnapshot=report();
    for(const ack of pending.splice(0))bridge?.ack(JSON.stringify({...ack,...w.live2dSnapshot,ok:true}));
    if(now-lastReport>250){lastReport=now;bridge?.report(JSON.stringify(w.live2dSnapshot));}
    scheduleFrame();
  }catch(e){fail(e);}
}
async function main(){
  if(w.qt)await new Promise<void>(resolve=>new w.QWebChannel(w.qt.webChannelTransport,(channel:any)=>{bridge=channel.objects.petBridge;bridge.command.connect((s:string)=>command(JSON.parse(s)));resolve();}));
  gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:true,preserveDrawingBuffer:true})!;
  if(!gl)throw Error('WebGL unavailable');
  CubismFramework.startUp();CubismFramework.initialize();
  const url=new URL('../model/'+new URLSearchParams(location.search).get('model'),location.href);
  const settings=JSON.parse(new TextDecoder().decode(await buffer(url.href))),resource=(file:string)=>new URL(file,url).href;
  user=new PetModel();user.loadModel(await buffer(resource(settings.FileReferences.Moc)),true);
  const m=user.getModel();
  for(let i=0;i<m.getParameterCount();i++)params.push({index:i,id:m.getParameterId(i).getString(),default:m.getParameterDefaultValue(i),min:m.getParameterMinimumValue(i),max:m.getParameterMaximumValue(i)});
  for(const p of params)paramById.set(p.id,p);
  m.update();let xmin=Infinity,xmax=-Infinity,ymin=Infinity,ymax=-Infinity;
  for(let i=0;i<m.getDrawableCount();i++){if(m.getDrawableOpacity(i)<.01)continue;const v=m.getDrawableVertices(i);for(let j=0;j<v.length;j+=2){xmin=Math.min(xmin,v[j]);xmax=Math.max(xmax,v[j]);ymin=Math.min(ymin,v[j+1]);ymax=Math.max(ymax,v[j+1]);}}
  bounds={x:(xmin+xmax)/2,y:(ymin+ymax)/2,width:xmax-xmin,height:ymax-ymin};
  user.createRenderer();const renderer=user.getRenderer();renderer.startUp(gl);renderer.setIsPremultipliedAlpha(true);
  for(let i=0;i<settings.FileReferences.Textures.length;i++){
    const im=new Image();im.src=resource(settings.FileReferences.Textures[i]);await im.decode();const tex=gl.createTexture()!;
    gl.bindTexture(gl.TEXTURE_2D,tex);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,true);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,im);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);renderer.bindTexture(i,tex);
  }
  renderer.loadShaders(new URL('vendor/Framework/Shaders/WebGL/',location.href).href);
  const pd=await buffer(resource(settings.FileReferences.Physics));user.loadPhysics(pd,pd.byteLength);
  const physics=JSON.parse(new TextDecoder().decode(pd));physicsOutputs=[...new Set(physics.PhysicsSettings.flatMap((s:any)=>s.Output.map((o:any)=>o.Destination.Id)))] as string[];
  contract=JSON.parse(new TextDecoder().decode(await buffer(resource('emotion-contract.json'))));
  capabilities.expressions=contract.expressions.map((e:any)=>e.name);
  const expressions=new Map();
  for(const entry of contract.expressions){const data=await buffer(resource(entry.file));expressions.set(entry.name,CubismExpressionMotion.create(data,data.byteLength));}
  if(contract.thinkingAction){const data=await buffer(resource(contract.thinkingAction.file));const motion=CubismMotion.create(data,data.byteLength,undefined,undefined,true);motion.setLoop(false);motion.setEffectIds([],[]);thought=createThoughtController({model:m,manager:new CubismMotionManager(),motion,exitFade:contract.thinkingAction.exitFadeSeconds});}
  emotion=createEmotionController({model:m,contract,manager:new CubismExpressionMotionManager(),motions:expressions,onChange:({name}:any)=>{if(name==='thinking')thought?.start();else thought?.cancel();}});
  const singContract=JSON.parse(new TextDecoder().decode(await buffer(resource('sing.action.json')))),motionData:any={};
  for(const [key,file]of Object.entries(singContract.resources))motionData[key]=JSON.parse(new TextDecoder().decode(await buffer(resource(String(file)))));
  singer=createSingingController({model:m,manager:new CubismMotionManager(),contract:singContract,motionData,getId:(id:string)=>CubismFramework.getIdManager().getId(id),createMotion:(doc:any)=>{const data=new TextEncoder().encode(JSON.stringify(doc));return CubismMotion.create(data.buffer,data.byteLength,undefined,undefined,true);}});
  advance=createFrameDriver({resetBase:()=>{for(const p of params)m.setParameterValueByIndex(p.index,p.default);},updateMotion,
    stabilizePhysics:()=>{resetPhysics=true;},updatePhysics:(dt:number)=>{user.physics(dt,resetPhysics);resetPhysics=false;for(const id of physicsOutputs){const limit=id==='ParamEyeBallForm'||id==='ParamTearSway'?1:.6;set(id,Math.max(-limit,Math.min(limit,get(id))));}}});
  ready=true;w.live2d={command,snapshot:report};w.live2dSnapshot=report();bridge?.report(JSON.stringify(report()));last=performance.now();scheduleFrame();
}
document.addEventListener('visibilitychange',scheduleFrame);
canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();fail('WebGL context lost; reload required');});
main().catch(fail);
