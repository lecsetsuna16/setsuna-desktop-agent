// Count all animation time while keeping physics steps bounded. No browser APIs.
// After a long suspension, skip obsolete physics and stabilize at the current pose.
export function createFrameDriver({resetBase,updateMotion,updatePhysics,stabilizePhysics,physicsStep=1/120,maxCatchUp=.25}){
  if(!(physicsStep>0&&Number.isFinite(physicsStep)&&maxCatchUp>=physicsStep&&Number.isFinite(maxCatchUp)))throw Error('Invalid physics timing');
  return function advance(dt){
    if(!Number.isFinite(dt)||dt<0)throw Error('dt must be finite and nonnegative');
    const skipped=Math.max(0,dt-maxCatchUp);let remaining=dt-skipped,count=0,maxStep=0;
    if(skipped>0){resetBase();updateMotion(skipped);stabilizePhysics();}
    while(remaining>1e-12){const step=Math.min(physicsStep,remaining);resetBase();updateMotion(step);updatePhysics(step);remaining=Math.max(0,remaining-step);count++;maxStep=Math.max(maxStep,step);}
    if(dt===0){resetBase();updateMotion(0);}
    return {animationSeconds:dt,physicsSeconds:dt-skipped,skippedPhysicsSeconds:skipped,physicsSteps:count,maxPhysicsStep:maxStep};
  };
}
