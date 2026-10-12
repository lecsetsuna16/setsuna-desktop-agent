// SDK host adapter. The host supplies its dedicated exclusive CubismMotionManager and motion parser.
// This module does not draw a prop overlay or implement a second animation engine.
export function createSingingController({model, manager, createMotion, contract, motionData, getId}) {
  const ids=contract.drivenParameters;
  const get=(id)=>model.getParameterValueById(getId(id));
  const set=(id,v)=>model.setParameterValueById(getId(id),v);
  const snapshot=()=>Object.fromEntries(ids.map(id=>[id,get(id)]));
  let state='idle',elapsed=0,loopElapsed=0,duration=16,restore={...contract.restPose},active=null,lastDrivenPose=null;
  const log=[];
  function setState(next){state=next;elapsed=0;log.push({state:next});}
  function begin(doc,loop=false){manager.stopAllMotions();active=createMotion(doc);active.setLoop(loop);active.setFadeInTime(0);active.setFadeOutTime(0);active.setEffectIds([],[]);manager.startMotionPriority(active,false,3);manager.updateMotion(model,0);}
  function transition(template,from,to,entering) {
    const doc=JSON.parse(JSON.stringify(template)),D=doc.Meta.Duration;
    for(const c of doc.Curves){const k=c.Id,steps=Math.round(D*30),v0=from[k]??0,v1=to[k]??0;
      c.Segments=[0,k==='ParamMicrophone'?0:v0];
      for(let i=1;i<=steps;i++){const t=i/steps;let u=t*t*(3-2*t);if(k==='ParamArmAction'||k==='ParamSingingGrip'){const time=t*D;let s=entering?(k==='ParamArmAction'?time/2.6:(time-2.4)/1.8):(k==='ParamSingingGrip'?time/1.8:(time-1.8)/2.4);s=Math.max(0,Math.min(1,s));u=s*s*(3-2*s);}if(entering&&(k==='ParamMouthForm'||k==='ParamMouthOpenY')){let s=Math.max(0,Math.min(1,(t*D-2.6)/(D-2.6)));u=s*s*(3-2*s);}c.Segments.push(k==='ParamMicrophone'?2:0,D*t,k==='ParamMicrophone'?0:v0+(v1-v0)*u);}
    }
    return doc;
  }
  function start(seconds=16){
    if(typeof seconds!=='number'||!Number.isFinite(seconds)||seconds<1||seconds>300)throw Error('durationSeconds must be 1..300');
    if(state!=='idle')return {action:'sing',state,accepted:false,reason:'busy',queued:false,alreadyRunning:true};
    restore=snapshot();restore.ParamMicrophone=0;lastDrivenPose={...restore};duration=seconds;loopElapsed=0;
    begin(transition(motionData.enter,restore,contract.loopAnchor,true));setState('enter');return {action:'sing',state,durationSeconds:duration};
  }
  // The host resets base parameters before update(). Natural completion must use the
  // last driven pose, rather than that transient base pose. Manual stops use the same cache.
  function stop(){if(state==='idle'||state==='exit')return {action:'sing',state};const from=lastDrivenPose||snapshot();begin(transition(motionData.exit,from,restore,false));setState('exit');return {action:'sing',state};}
  function reset(){manager.stopAllMotions();active=null;lastDrivenPose=null;setState('idle');for(const id of ids)set(id,restore[id]);set('ParamMicrophone',0);return {action:'sing',state};}
  function update(dt,sustain=false){
    if(!Number.isFinite(dt)||dt<0)throw Error('dt must be finite and nonnegative');
    let remaining=dt;
    // Consume each boundary at its exact time, including several phases in one tick.
    // Any time after exit belongs to the ordinary motion, not to the finished action.
    while(state!=='idle'){
      const limit=state==='enter'?motionData.enter.Meta.Duration:state==='loop'?(sustain?Infinity:duration):motionData.exit.Meta.Duration;
      const step=Math.min(remaining,Math.max(0,limit-elapsed));
      manager.updateMotion(model,step);elapsed+=step;remaining=Math.max(0,remaining-step);
      if(state==='loop')loopElapsed=elapsed;
      set('ParamMicrophone',state==='loop'?1:0);lastDrivenPose=snapshot();
      if(elapsed>=limit-1e-9){
        if(state==='enter'){setState('loop');begin(motionData.loop,true);set('ParamMicrophone',1);lastDrivenPose=snapshot();}
        else if(state==='loop')stop();
        else reset();
      }else break;
      if(remaining<=1e-12)break;
    }
    return remaining;
  }
  function dispatch(request){if(!request||request.action!=='sing')throw Error('Unsupported action');if(request.command==='start')return start(request.durationSeconds??16);if(request.command==='stop')return stop();throw Error('command must be start or stop');}
  return {start,stop,reset,update,dispatch,get state(){return state},get status(){return {state,elapsed,loopElapsed,durationSeconds:duration}},log};
}
