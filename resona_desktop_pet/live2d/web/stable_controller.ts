export type Range={min:number,max:number,tau:number,speed:number};
export class StableController {
 state:Record<string,number>={};
 constructor(public ranges:Record<string,Range>,public parameters:any[]){for(const p of parameters)this.state[p.id]=p.default;}
 normalized(input:Record<string,number>){const out:Record<string,number>={};for(const [id,v] of Object.entries(input)){const r=this.ranges[id],p=this.parameters.find(p=>p.id===id);if(!r||!p)continue;const n=Number.isFinite(v)?Math.max(-1,Math.min(1,v)):0;out[id]=p.default+n*(n<0?p.default-r.min:r.max-p.default);}return out;}
 step(input:Record<string,number>,dt:number,ids?:string[]){
  const out:Record<string,number>={};dt=Number.isFinite(dt)?Math.max(0,Math.min(.05,dt)):0;
  for(const p of this.parameters){if(ids&&!ids.includes(p.id))continue;const r=this.ranges[p.id];if(!r)throw Error('Missing stable range: '+p.id);
   const raw=input[p.id]??p.default,prev=this.state[p.id];
   const target=Math.max(r.min,Math.min(r.max,Number.isFinite(raw)?raw:prev));
   const delta=(target-prev)*(r.tau>0?1-Math.exp(-dt/r.tau):1),limit=r.speed>0?r.speed*dt:Infinity;
   const value=Math.max(r.min,Math.min(r.max,prev+Math.max(-limit,Math.min(limit,delta))));
   this.state[p.id]=out[p.id]=value;
  }return out;
 }
}
