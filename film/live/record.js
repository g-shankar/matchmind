const { chromium } = require('playwright');
const fs=require('fs');
const B=process.env.BASE||'https://ca-pitchpulse.wonderfulbush-438b1d1e.swedencentral.azurecontainerapps.io/';
const VP={width:1920,height:1080};
async function seg(b,name,fn){
  const c=await b.newContext({viewport:VP,recordVideo:{dir:'v/'+name,size:VP}});
  const p=await c.newPage(); const t0=Date.now(); const marks=[];
  const mark=async(l)=>{marks.push([l,(Date.now()-t0)/1000]); await p.screenshot({path:`s_${name}_${marks.length}_${l}.png`});};
  const tryc=async(loc,ms=3000)=>{try{await loc.first().click({timeout:ms});return true}catch(e){console.log(name,'miss',String(loc));return false}};
  try{await fn(p,mark,tryc)}catch(e){console.log(name,'ERR',e.message)}
  await c.close(); fs.writeFileSync(`v/${name}.json`,JSON.stringify(marks)); console.log(name,JSON.stringify(marks));
}
(async()=>{const b=await chromium.launch();
const only=process.argv[2];
const S={
 studio: async(p,mark,tryc)=>{
  await p.goto(B+'?t=2052&p=1&lang=en#studio',{waitUntil:'domcontentloaded'});
  await p.waitForTimeout(7000); await mark('start');
  await p.waitForTimeout(6000); await mark('shot');
  await tryc(p.getByRole('button',{name:'Show the replay'}),8000); await p.waitForTimeout(1500); await mark('replay');
  await p.waitForTimeout(12000); await mark('replay_end');
  await tryc(p.locator('[data-testid=option-next]')); await p.waitForTimeout(3500); await mark('opt2');
  await tryc(p.locator('[data-testid=option-next]')); await p.waitForTimeout(3500); await mark('opt3');
 },
 camera: async(p,mark,tryc)=>{
  await p.goto(B+'?lang=en#studio',{waitUntil:'domcontentloaded'}); await p.waitForTimeout(7000); await mark('start');
  await tryc(p.locator('[data-testid=camera-control] [role=radio]').nth(1)); await p.waitForTimeout(4000); await mark('tactical');
  await tryc(p.locator('[data-testid=camera-control] [role=radio]').nth(2)); await p.waitForTimeout(5000); await mark('follow');
  await tryc(p.locator('[data-testid=camera-control] [role=radio]').nth(0));
 },
 split: async(p,mark,tryc)=>{
  for (const l of ['en','es','ar']){
   await p.goto(B+`?t=2062&p=1&pause=1&lang=${l}#split`,{waitUntil:'domcontentloaded'}); await p.waitForTimeout(6000);
   const sel=p.locator('main select, select').nth(1); try{const o=await sel.locator('option').allTextContents(); console.log(o); const i=o.findIndex(x=>x.includes('34:16')); if(i>=0) await sel.selectOption({index:i});}catch(e){console.log('sel',e.message)}
   await p.waitForTimeout(1500); await p.mouse.move(960,600); await p.mouse.wheel(0,750); await p.waitForTimeout(1200); await mark(l); await p.waitForTimeout(4000); await mark(l+'_end');
  }
 },
 stress: async(p,mark,tryc)=>{
  await p.goto(B+'?t=2100&p=1&lang=en#studio',{waitUntil:'domcontentloaded'}); await p.waitForTimeout(7000);
  await tryc(p.getByRole('tab',{name:/stats/i})) || await tryc(p.getByText(/^stats$/i)); await p.waitForTimeout(1500); await mark('stats');
  await tryc(p.getByRole('button',{name:'Stress test the crew'})); await p.waitForTimeout(2000); await mark('open');
  try{const s=p.locator('select').last(); const o=await s.locator('option').allTextContents(); console.log(o); const i=o.findIndex(x=>x.includes('34:16')); if(i>=0) await s.selectOption({index:i});}catch(e){console.log(e.message)}
  await tryc(p.getByRole('button',{name:'Run the test'})); await p.waitForTimeout(9000); await mark('result'); await p.mouse.wheel(0,500); await p.waitForTimeout(3000); await mark('result2');
 },
};
for (const [n,f] of Object.entries(S)) if(!only||only===n) await seg(b,n,f);
await b.close()})();
