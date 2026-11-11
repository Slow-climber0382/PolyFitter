import './browser-files.mjs';
import {createHistory} from './history.mjs';
import {geometryTask} from './worker.mjs';
import {kitParts,setKitTransform,kitMesh,fitColors} from './helmet.mjs';
import {splitForPrinter} from './cut.mjs';
import {mountMeasurements} from './measurements.mjs';
import {autoFit,bounds,centerMesh,demoShell,evaluate,identity,inspectMesh,parseSTL,transform,writeSTL} from './geometry.mjs';
import {createViewport} from './viewport.mjs';
import {BODY_TYPES,DETAILS,profileDetails,headCircumference,resizeHeadCircumference} from './avatar.mjs';
import {BODY_VIEWS,POSES,fittingView,humanScene,humanFittingVolumes,humanAudit,fittingDimensions} from './human.mjs';
import {freshProfile,MAX_PROJECT_BYTES,MAX_PROJECT_FACES,openProject,packProject,REGIONS,SHIN_STYLES,DEFAULT_SHIN_STYLE} from './project.mjs';

const $=id=>document.getElementById(id);
const canvas=$('viewport');
let viewport;
try{viewport=createViewport(canvas);}
catch(error){$('renderError').textContent=error.message;$('renderError').hidden=false;}
let profile=freshProfile(), parts=[],active=-1,region='head',projectName='Nowy projekt',dirty=false;
const selected=()=>parts[active];
const measurement=()=>profile[region];
let colorCache=null,colorBusy=false;
let viewRegion='full',pose='side',detailsRegion=null;
for(const [value,label] of Object.entries(BODY_VIEWS))$('previewRegion').add(new Option(label,value));
for(const [value,label] of Object.entries(POSES))$('pose').add(new Option(label,value));
for(const [value,label] of Object.entries(BODY_TYPES))$('bodyType').add(new Option(label,value));
const currentShinStyle=()=>selected()?.shinStyle??DEFAULT_SHIN_STYLE;
const currentSide=()=>selected()?.shinSide??'L';
for(const [value,label] of Object.entries(SHIN_STYLES))$('shinStyle').add(new Option(label,value));
const status=message=>$('status').textContent=message;
const format=n=>Number(n.toFixed(3)).toString();
let pendingHistory=false,restoringHistory=false;
const historyState=()=>({profile,parts,active,region,projectName});
const history=createHistory(historyState());
function historyButtons(){$('undo').disabled=!history.canUndo;$('redo').disabled=!history.canRedo;}
function travelHistory(direction){const state=history[direction]();if(!state)return;restoringHistory=true;({profile,parts,active,region,projectName}=state);colorCache=null;viewRegion=selected()?fittingView(region,currentSide()):'full';setDirty();sync();restoringHistory=false;status(direction==='undo'?'Cofnięto zmianę.':'Ponowiono zmianę.');}
$('undo').onclick=()=>travelHistory('undo');$('redo').onclick=()=>travelHistory('redo');
window.addEventListener('keydown',event=>{if(!(event.ctrlKey||event.metaKey)||event.altKey)return;if(event.target.matches('input,textarea,[contenteditable=true]'))return;if(event.key.toLowerCase()==='z'){event.preventDefault();travelHistory(event.shiftKey?'redo':'undo');}});
function setDirty(value=true){if(value&&!restoringHistory)pendingHistory=true;dirty=value;$('projectTitle').textContent=projectName+(dirty?'  •':'');}
window.addEventListener('beforeunload',event=>{
  if(dirty){event.preventDefault();event.returnValue=true;}
});
const hints={
  head:'Wysokość od podbródka do czubka głowy. Otwór hełmu powinien być skierowany w dół (−Y).',
  chest:'Wysokość obszaru od góry do dołu napierśnika. Ustaw stronę zewnętrzną w kierunku +Z.',
  shin:'Zmierz szerokość i głębokość w najszerszym miejscu. Oś nogi powinna pokrywać się z Y.'
};
const transformFields={};
for(const [key,label,units,min,max,step] of [
  ['scale','Skala','%',0.5,5000,0.1],
  ['rotate','Obrót','°',-360,360,1],
  ['offset','Przesunięcie','mm',-5000,5000,1]
]){
  const title=document.createElement('div');title.className='group-label';title.textContent=label+' · '+units;
  const row=document.createElement('div');row.className='three';
  transformFields[key]=['X','Y','Z'].map((axis,index)=>{
    const field=document.createElement('label');field.textContent=axis;
    const input=document.createElement('input');input.type='number';input.min=min;input.max=max;input.step=step;
    input.id=key+index;input.setAttribute('aria-label',label+' '+axis+' '+units);
    field.append(input);row.append(field);
    input.addEventListener('change',()=>{
      const part=selected();if(!part)return;
      if(!readNumber(input,min,max)){sync();return;}
      const value=Number(input.value)/(key==='scale'?100:1);
      if(key==='scale'&&$('lockScale').checked)part.transform.scale.fill(value);
      else part.transform[key][index]=value;
      setDirty();sync();
    });
    return input;
  });
  $('transforms').append(title,row);
}
function readNumber(input,min,max){
  const value=input.valueAsNumber;
  if(Number.isFinite(value)&&value>=min&&value<=max)return true;
  status(`Wpisz liczbę w zakresie ${min}–${max}.`);return false;
}
function refreshParts(){
  const list=$('parts');list.replaceChildren();
  parts.forEach((part,i)=>{
    const item=document.createElement('li'), button=document.createElement('button');
    button.type='button';button.className='part';button.setAttribute('aria-current',String(i===active));
    const title=document.createElement('strong'), info=document.createElement('small');
    title.textContent=part.name;title.title=part.name;info.textContent=part.group?'Zestaw hełmu':part.region==='shin'?SHIN_STYLES[part.shinStyle??DEFAULT_SHIN_STYLE]:REGIONS[part.region].part;
    button.append(title,info);item.append(button);list.append(item);
    button.onclick=()=>{active=i;region=part.region;viewRegion=fittingView(region,currentSide());setDirty();sync();};
  });
  $('partCount').textContent=parts.length;
}
function syncMeasurements(){
  const {dimensions,details}=measurement();
  $('headQuick').hidden=region!=='head';
  $('bodyQuick').hidden=false;
  $('headHeight').value=dimensions[1];
  $('headCirc').value=format(headCircumference(dimensions));
  $('bodyType').value=profile.avatar.type;
  $('stature').value=profile.avatar.stature;
  for(let i=0;i<3;i++)$('dim'+i).value=format(dimensions[i]);
  $('heightDetail').hidden=region==='head';
  if(detailsRegion!==region){
    const fields=$('detailFields');
    fields.replaceChildren();
    for(const [key,{label,min,max}] of Object.entries(DETAILS[region])){
      const field=document.createElement('label');field.textContent=label;
      const input=document.createElement('input');input.type='number';input.min=min;input.max=max;input.step=1;
      input.id='measure-'+key;
      input.onchange=()=>{
        if(readNumber(input,min,max)){measurement().details[key]=input.valueAsNumber;setDirty();}
        sync();
      };
      field.append(input);fields.append(field);
    }
    detailsRegion=region;
  }
  const values=profileDetails(profile,region);
  for(const [key,value] of Object.entries(values))$('measure-'+key).value=value;
  $('clearDetails').disabled=!Object.keys(details).length;
}
function report(part,mesh,checkEntry){
  const {dimensions,gap}=measurement(), result=evaluate(mesh,region,dimensions,gap,part.quality,{entry:checkEntry,avatar:humanFittingVolumes(profile,region,currentSide())});
  const report=$('fitReport');
  report.dataset.tone=(result.collision||result.entry==='blocked')?'bad':result.margin+0.01<gap?'bad':'ok';
  const lines=[result.solid?'Obrys znajduje się wewnątrz pełnej bryły.':
    result.collision?'Model przecina manekin.':
    `Szacowany minimalny luz ≥ ${format(result.margin)} mm. Orientacja i położenie wizjera wymagają kontroli.`];
  if(!result.collision&&result.margin+0.01<gap)lines.push('Wynik jest poniżej zadanego luzu.');
  if(result.entry==='blocked')lines.push('Próba wsunięcia od dołu wykryła kolizję.');
  if(result.entry==='clear')lines.push('Próbki wsunięcia od dołu bez kolizji.');
  if(result.entry==='unknown')lines.push('Droga wsunięcia jest za długa do tej kontroli.');
  report.textContent=lines.join(' ');
}
function sync(checkEntry=false){
  const part=selected(),{dimensions,gap}=measurement();
  if(part?.group)setKitTransform(parts,part,part.transform);
  $('solvePlacement').parentElement.hidden=region!=='head';$('helmetTools').hidden=region!=='head';$('foamTop').value=profile.head.foamTop??0;
  for(const id of ['moveUp','moveDown','moveFront','moveBack','tiltUp','tiltDown','exportKit','splitPrint'])$(id).disabled=!part;
  $('heatmapLegend').hidden=!$('heatmap').checked;
  const audit=humanAudit(profile);
  $('anatomyAudit').textContent=`Wzrost ${audit.stature.toFixed(1)} mm · głowa ${audit.headHeight.toFixed(1)} mm · obwód ${audit.headCircumference.toFixed(1)} mm · 1:${audit.headRatio.toFixed(2)} · szyja ${audit.neckLength.toFixed(1)} mm · barki ${audit.shoulderWidth.toFixed(1)} mm. Obwód na poziomej linii czoła; barki na górnej linii mięśni naramiennych.`;
  $('region').value=region;
  $('shinStyleField').hidden=region!=='shin'||!part;
  $('shinStyle').value=currentShinStyle();$('shinSide').value=currentSide();
  $('regionHint').textContent=region==='shin'&&currentShinStyle()==='front'
    ?'Zmierz obszar, który ma zakrywać płyta. Ustaw jej przód w kierunku +Z i wysokość wzdłuż Y.'
    :hints[region];
  $('regionPill').textContent=REGIONS[region].label;$('viewTitle').textContent=part?.name||'Widok 3D';
  $('viewTitle').title=part?.name||'';
  $('empty').hidden=Boolean(part)||!viewport;
  syncMeasurements();
  $('gap').value=gap;
  for(const key of ['fit','export','remove','reset','zUp','flipFront'])$(key).disabled=!part;
  for(const [key,fields] of Object.entries(transformFields)){
    fields.forEach((field,i)=>{field.disabled=!part;field.value=format((part?.transform[key][i]??identity()[key][i])*(key==='scale'?100:1));});
  }
  $('entryCheck').hidden=!part||region!=='head';
  $('previewRegion').value=viewRegion;$('pose').value=pose;
  $('poseHint').hidden=pose==='standing';
  if(part){
    const mesh=kitMesh(parts,part), q=part.quality;
    report(part,mesh,checkEntry);
    $('meshReport').textContent=`${q.faces.toLocaleString('pl-PL')} trójkątów · ${q.boundary} otwartych krawędzi · ${q.nonManifold} krawędzi wielokrotnych · ${q.degenerate} zdegenerowanych ścian`;
    $('sizeStatus').textContent=bounds(mesh).size.map(n=>n.toFixed(1)).join(' × ')+' mm';
    if(viewport){
      const showPart=viewRegion==='full'||viewRegion===fittingView(region,currentSide())||(region==='chest'&&viewRegion==='chest');
      const scene=humanScene(profile,viewRegion,pose,showPart?mesh:null,region,currentSide());
      const colorKey=JSON.stringify({active,profile,parts:parts.map(p=>[p.name,p.transform]),region});
      let colors=null;
      if($('heatmap').checked&&scene.mesh){
        if(colorCache?.key===colorKey)colors=colorCache.colors;
        else if(!colorBusy){
          colorBusy=true;status('Obliczanie mapy dopasowania…');
          geometryTask('colors',mesh.slice().buffer,[humanFittingVolumes(profile,region,currentSide()),gap]).then(result=>{
            colorCache={key:colorKey,colors:new Float32Array(result.colors)};colorBusy=false;sync();status('Mapa dopasowania gotowa — przybliżona odległość od obwiedni ciała.');
          }).catch(error=>{colorBusy=false;$('heatmap').checked=false;status(error.message);sync();});
        }
      }
      viewport.scene(scene.mesh,scene.context,scene.body,scene.seams,colors);
    }
  }else{
    $('fitReport').textContent='Dodaj model, aby sprawdzić dopasowanie.';
    delete $('fitReport').dataset.tone;
    $('meshReport').textContent='';$('sizeStatus').textContent='Jednostki projektu: mm';
    if(viewport){
      const scene=humanScene(profile,viewRegion,pose);
      viewport.scene(null,scene.context,scene.body,scene.seams);
    }
  }
  refreshParts();refreshPersonalMeasurements();
  if(pendingHistory&&!restoringHistory){history.commit(historyState());pendingHistory=false;}historyButtons();
}
function addPart(name,mesh,bodyRegion,quality=inspectMesh(mesh)){
  if(parts.length>=100||mesh.length/9+parts.reduce((n,p)=>n+p.quality.faces,0)>MAX_PROJECT_FACES)
    throw Error('Projekt może zawierać do 100 części i 2 000 000 trójkątów.');
  if(mesh.some(v=>!Number.isFinite(v)||Math.abs(v)>1e7))throw Error('Model ma zbyt duże wymiary. Sprawdź jednostki importu.');
  parts.push({name:name.slice(0,120),mesh,region:bodyRegion,quality,transform:identity()});
  active=parts.length-1;region=bodyRegion;viewRegion=fittingView(region,currentSide());setDirty();sync();
  status('Model dodany. Sprawdź orientację i uruchom dopasowanie.');
}
async function fileAction(event,action){
  const file=event.target.files[0];event.target.value='';
  if(!file)return;
  try{await action(file);}catch(error){status(error.message);$('importReport').textContent=error.message;}
}
$('modelFile').onchange=event=>fileAction(event,async file=>{
  if(file.size>MAX_PROJECT_BYTES)throw Error('Plik STL przekracza 150 MB.');
  const bodyRegion=region,unit=Number($('units').value);
  $('importReport').textContent='Wczytywanie i kontrola siatki…';status('Wczytywanie '+file.name+'…');
  const parsed=await geometryTask('parse',await file.arrayBuffer());
  const mesh=new Float32Array(parsed.mesh);
  addPart(file.name.replace(/\.stl$/i,'').trim()||'Element',centerMesh(mesh,unit),bodyRegion,parsed.quality);
  $('importReport').textContent=`Wczytano ${parsed.quality.faces.toLocaleString('pl-PL')} trójkątów. Rozmiar: ${bounds(mesh).size.map(v=>(v*unit).toFixed(1)).join(' × ')} mm. STL nie zapisuje jednostek — sprawdź mm/cm/cale.`;
  viewport?.view('selected');
});
$('projectFile').onchange=event=>fileAction(event,async file=>{
  if(dirty&&!confirm('Otworzyć inny projekt i odrzucić niezapisane zmiany?'))return;
  if(file.size>MAX_PROJECT_BYTES)throw Error('Plik projektu przekracza 150 MB.');
  const restored=openProject(await file.text());
  ({profile,parts,active}=restored);
  region=selected()?.region||'head';viewRegion='full';pose='side';
  projectName=file.name.replace(/\.(forgefit|meshavon|polyfitter)$/i,'')||'Projekt';setDirty(false);pendingHistory=false;history.reset(historyState());sync();status('Projekt wczytany.');
});
for(const id of ['import','emptyImport'])$(id).onclick=()=>$('modelFile').click();
$('open').onclick=()=>$('projectFile').click();
$('newProject').onclick=()=>{
  if(dirty&&!confirm('Utworzyć nowy projekt i odrzucić niezapisane zmiany?'))return;
  profile=freshProfile();parts=[];active=-1;region='head';viewRegion='full';pose='side';projectName='Nowy projekt';setDirty(false);pendingHistory=false;history.reset(historyState());sync();status('Nowy projekt.');
};
$('demo').onclick=()=>{try{addPart('Hełm demonstracyjny',centerMesh(demoShell()),'head');}catch(error){status(error.message);}};
$('remove').onclick=()=>{
  if(!selected())return;
  parts.splice(active,1);active=Math.min(active,parts.length-1);
  region=selected()?.region||region;setDirty();sync();status('Element usunięty z projektu.');
};
$('region').onchange=event=>{
  region=event.target.value;viewRegion=fittingView(region,currentSide());
  if(selected()){if(selected().group&&region!=='head'){status('Zestaw pozostaje przypisany do hełmu.');region='head';}selected().region=region;setDirty();}
  sync();
};
$('shinSide').onchange=event=>{
  const part=selected();
  if(part?.region!=='shin')return;
  part.shinSide=event.target.value;viewRegion=fittingView(region,currentSide());
  setDirty();sync();
};
$('shinStyle').onchange=event=>{
  const part=selected();
  if(part?.region!=='shin')return;
  part.shinStyle=event.target.value;
  setDirty();sync();status('Typ ochraniacza zmieniony. Kliknij „Dopasuj automatycznie”, aby przeliczyć ustawienie.');
};
for(let i=0;i<3;i++)$('dim'+i).onchange=event=>{
  if(readNumber(event.target,10,2000)){measurement().dimensions[i]=event.target.valueAsNumber;setDirty();}
  sync();
};
$('headHeight').onchange=event=>{
  if(readNumber(event.target,100,360)){profile.head.dimensions[1]=event.target.valueAsNumber;profile.avatar.headMeasured=true;setDirty();}
  sync();
};
$('headCirc').onchange=event=>{
  if(readNumber(event.target,300,1000)){
    profile.head.dimensions=resizeHeadCircumference(profile.head.dimensions,event.target.valueAsNumber);profile.avatar.headMeasured=true;
    setDirty();
  }
  sync();
};
$('bodyType').onchange=event=>{profile.avatar.type=event.target.value;setDirty();sync();};
$('stature').onchange=event=>{
  if(readNumber(event.target,800,2500)){
    const next=event.target.valueAsNumber, ratio=next/profile.avatar.stature;
    if(!profile.avatar.headMeasured)profile.head.dimensions=profile.head.dimensions.map(v=>v*ratio);
    for(const key of ['chest','shin'])profile[key].dimensions=profile[key].dimensions.map(v=>Math.min(2000,Math.max(10,Math.round(v*ratio))));
    profile.avatar.stature=next;setDirty();
  }
  sync();
};
$('clearDetails').onclick=()=>{measurement().details={};setDirty();sync();};
$('previewRegion').onchange=event=>{viewRegion=event.target.value;viewport?.view('reset');sync();};
$('pose').onchange=event=>{pose=event.target.value;viewRegion='full';viewport?.view('reset');sync();};
$('gap').onchange=event=>{
  if(readNumber(event.target,0,100)){measurement().gap=event.target.valueAsNumber;setDirty();}
  sync();
};
$('fit').onclick=async()=>{
  const part=selected();if(!part)return;
  const input=JSON.stringify({profile,transform:part.transform,region,side:currentSide()});
  $('fit').disabled=true;status('Obliczanie skali i luzu…');
  try{
    const {dimensions,gap}=measurement();
    const {result}=await geometryTask('fit',part.mesh.slice().buffer,[region,region==='chest'?fittingDimensions(profile,region,currentSide()):dimensions,gap,part.transform.rotate,part.quality,currentShinStyle(),humanFittingVolumes(profile,region,currentSide()),part.transform.offset,$('solvePlacement').checked]);
    if(part!==selected()||input!==JSON.stringify({profile,transform:part.transform,region,side:currentSide()})){status('Dane zmieniły się podczas obliczeń. Uruchom dopasowanie ponownie.');return;}
    part.transform=result;setDirty();sync(region==='head');status('Zastosowano proponowaną skalę i położenie. Sprawdź orientację i położenie oczu/brody.');
  }catch(error){status(error.message);$('fitReport').textContent=error.message;}
  finally{$('fit').disabled=!selected();}
};
$('entryCheck').onclick=()=>sync(true);
$('reset').onclick=()=>{
  const part=selected();if(!part)return;
  part.transform={...identity(),rotate:[...part.transform.rotate]};setDirty();sync();status('Przywrócono skalę i położenie.');
};
function safeName(name){return name.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').trim().slice(0,120)||'PolyFitter';}
$('save').onclick=async()=>{
  try{
    if(await window.forgefit.save(safeName(projectName)+'.polyfitter',packProject(profile,parts,active))){
      setDirty(false);status('Rozpoczęto pobieranie projektu. Sprawdź pobrane pliki przeglądarki.');
    }
  }catch(error){status(error.message);$('importReport').textContent=error.message;}
};
$('export').onclick=async()=>{
  const part=selected();if(!part)return;
  try{
    if(await window.forgefit.save(safeName(part.name)+'-dopasowany.stl',writeSTL(transform(part.mesh,part.transform))))status('Wyeksportowano STL w milimetrach.');
  }catch(error){status(error.message);$('importReport').textContent=error.message;}
};
document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>{
  viewport?.view(button.dataset.view);
  if(button.hasAttribute('aria-pressed'))button.setAttribute('aria-pressed',String(button.getAttribute('aria-pressed')!=='true'));
});
const refreshPersonalMeasurements=mountMeasurements({getProfile:()=>profile,changed:()=>{setDirty();sync();}});
setDirty(false);sync();

$('foamTop').onchange=e=>{if(readNumber(e.target,0,40)){profile.head.foamTop=e.target.valueAsNumber;setDirty();}sync();};
$('noExtraGap').onclick=()=>{profile.head.gap=0;setDirty();sync();};
$('heatmap').onchange=()=>sync();
for(const [id,key,axis,delta] of [['moveUp','offset',1,1],['moveDown','offset',1,-1],['moveFront','offset',2,1],['moveBack','offset',2,-1],['tiltUp','rotate',0,1],['tiltDown','rotate',0,-1]])$(id).onclick=()=>{
 const part=selected();if(!part)return;const next=part.transform[key][axis]+delta;
 if(Math.abs(next)>(key==='rotate'?360:5000))return;
 part.transform[key][axis]=next;setDirty();sync();
};
$('importKit').onclick=()=>$('kitFiles').click();
$('kitFiles').onchange=async event=>{
 const files=[...event.target.files];event.target.value='';if(!files.length)return;
 try{
  if(files.length+parts.length>100||files.reduce((n,f)=>n+f.size,0)>MAX_PROJECT_BYTES)throw Error('Zestaw przekracza limit projektu.');
  const entries=[];for(const file of files){
    $('importReport').textContent='Wczytywanie zestawu: '+file.name;
    const parsed=await geometryTask('parse',await file.arrayBuffer());
    entries.push({name:file.name.replace(/\.stl$/i,'').slice(0,110),mesh:new Float32Array(parsed.mesh),quality:parsed.quality});
  }
  const additions=kitParts(entries,Number($('units').value));
  if(additions.reduce((n,p)=>n+p.mesh.length/9,0)+parts.reduce((n,p)=>n+p.quality.faces,0)>MAX_PROJECT_FACES)throw Error('Za dużo trójkątów w zestawie.');
  for(const part of additions){if(part.mesh.some(v=>!Number.isFinite(v)||Math.abs(v)>1e7))throw Error('Nietypowe współrzędne zestawu. Sprawdź jednostki.');part.quality??=inspectMesh(part.mesh);}
  active=parts.length;parts.push(...additions);$('importReport').textContent='Wczytano '+additions.length+' oddzielnych plików zestawu.';region='head';viewRegion='head';setDirty();sync();
  status('Zestaw zachowuje wspólny układ współrzędnych STL. Wybierz skorupę przed dopasowaniem; skala i położenie obejmą cały zestaw.');
 }catch(error){status(error.message);$('importReport').textContent=error.message;}
};
$('exportKit').onclick=async()=>{
 const part=selected();if(!part)return;
 try{const members=parts.filter(p=>p===part||(part.group&&p.group===part.group));
  if(await window.forgefit.saveBatch(members.map((p,i)=>({name:String(i+1)+'-'+safeName(p.name)+'.stl',data:writeSTL(transform(p.mesh,p.transform))}))))status('Zapisano zestaw STL ze wspólnymi współrzędnymi.');
 }catch(error){status(error.message);$('importReport').textContent=error.message;}
};
$('splitPrint').onclick=async()=>{
 const part=selected();if(!part||!readNumber($('printLimit'),100,250))return;
 try{
  const pieces=splitForPrinter(transform(part.mesh,part.transform),$('printLimit').valueAsNumber);
  if(await window.forgefit.saveBatch(pieces.map((mesh,i)=>({name:safeName(part.name)+'-czesc-'+(i+1)+'.stl',data:writeSTL(mesh)}))))status(`Wyeksportowano ${pieces.length} szczelnych części. Wspólne współrzędne zachowano; ułóż części na stole w slicerze.`);
 }catch(error){status(error.message);$('importReport').textContent=error.message;}
};

$('zUp').onclick=()=>{const part=selected();if(!part)return;part.transform.rotate=[-90,0,0];setDirty();sync();viewport?.view('selected');status('Z modelu → Y sceny. Sprawdź przód i tył.');};
$('flipFront').onclick=()=>{const part=selected();if(!part)return;part.transform.rotate[1]=(part.transform.rotate[1]+180)%360;setDirty();sync();};
