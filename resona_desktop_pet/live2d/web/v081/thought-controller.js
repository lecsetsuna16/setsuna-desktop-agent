// Dedicated Cubism motion queue for thinking; never stops a host body/arm queue.
export function createThoughtController({model,manager,motion,exitFade=.35}){
 let starts=0,elapsed=0,ending=false;
 return {
  start(){manager.startMotionPriority(motion,false,2);starts++;elapsed=0;ending=false},
  cancel(){if(manager.isFinished())return;for(const entry of manager.getCubismMotionQueueEntries())if(entry&&!entry.isFinished())entry.setFadeOut(exitFade);ending=true},
  update(dt){if(!manager.isFinished())elapsed+=dt;manager.updateMotion(model,dt)},
  get state(){return {running:!manager.isFinished(),starts,elapsed,ending}}
 };
}
