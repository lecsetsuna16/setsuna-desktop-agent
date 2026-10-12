// Switch the two eye material families while closed, rather than cross-fading irises.
// Call after expression evaluation; ordinary expression/motion clocks keep advancing.
export function createAngryEyeTransition({closeSeconds=.10,closedSeconds=.10,openSeconds=.14,settleSeconds=.45}={}) {
 const reopen=closeSeconds+closedSeconds, openEnd=reopen+openSeconds;
 if(![closeSeconds,closedSeconds,openSeconds,settleSeconds].every(v=>Number.isFinite(v)&&v>0)||settleSeconds<openEnd)throw Error('Invalid eye handover timing');
 const switchAt=closeSeconds+closedSeconds/2;
 const smooth=x=>{x=Math.max(0,Math.min(1,x));return x*x*(3-2*x)};
 let active=null;
 function request({previous,name,fromFocus,toFocus}){
  if(previous!=='angry'&&name!=='angry'&&!active)return false;
  if(!Number.isFinite(fromFocus)||!Number.isFinite(toFocus))throw Error('Invalid eye branch');
  // An interrupted handover starts at its current lid cap; it never pops open first.
  const startCap=active?.cap??1;
  active={elapsed:0,fromFocus,toFocus,startCap,cap:startCap,switched:false,initialized:false};
  return true;
 }
 function apply(dt,pose){
  if(!Number.isFinite(dt)||dt<0)throw Error('Invalid eye handover time');
  if(!active)return null;
  // Cubism initializes a newly queued motion at its first update, after advancing
  // its clock. Start our clock there too: a suspended first frame must not expire
  // this guard before the SDK's expression fade has even started.
  if(active.initialized)active.elapsed+=dt;else active.initialized=true;
  const t=active.elapsed;
  active.cap=t<closeSeconds?active.startCap*(1-smooth(t/closeSeconds)):t<reopen?0:smooth((t-reopen)/openSeconds);
  active.switched=t>=switchAt;
  const result={focus:active.switched?active.toFocus:active.fromFocus,left:pose.left*active.cap,right:pose.right*active.cap};
  // Hold the chosen branch until the SDK's original expression fade has settled.
  if(t>=settleSeconds)active=null;
  return result;
 }
 return {request,apply,get state(){return active?{...active}:null}};
}
