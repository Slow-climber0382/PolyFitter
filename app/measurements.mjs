import {DETAILS,ARM_FIELDS,LEG_FIELDS,LIMB_FIELDS,limbValues,profileDetails,headCircumference,resizeHeadCircumference} from './avatar.mjs';
export const MEASUREMENT_GROUPS={head:'Hełm',chest:'Klatka piersiowa',armR:'Prawa ręka',armL:'Lewa ręka',legR:'Prawa noga',legL:'Lewa noga'};
function baseMeasurementFields(profile,group){
  const field=(key,label,value,min,max)=>({key,label,value,min,max});
  if(group==='head')return [
    field('height','Czubek głowy do brody',profile.head.dimensions[1],100,360),
    field('circ','Obwód głowy nad brwiami',headCircumference(profile.head.dimensions),300,1000),
    ...Object.entries(DETAILS.head).map(([key,f])=>({...f,key,value:profileDetails(profile,'head')[key]}))
  ];
  if(group==='chest')return [
    field('length','Długość tułowia (podstawa szyi–biodra)',profile.chest.dimensions[1],250,800),
    ...Object.entries(DETAILS.chest).filter(([key])=>!ARM_FIELDS.includes(key)&&!['backLength'].includes(key))
      .map(([key,f])=>({...f,key,value:profileDetails(profile,'chest')[key]}))
  ];
  const kind=group.slice(0,3),values=limbValues(profile,kind,group.at(-1));
  const keys=kind==='arm'?ARM_FIELDS:LEG_FIELDS;
  return [field('total',kind==='arm'?'Długość ręki (bark–nadgarstek)':'Długość nogi (biodro–kostka)',
    kind==='arm'?values.upperArmLength+values.forearmLength:values.thighLength+values.lowerLegLength,
    kind==='arm'?150:260,kind==='arm'?1200:1600),
    ...keys.map(key=>({...LIMB_FIELDS[key],key,value:values[key]}))];
}
const shapeKeys={head:['circ'],chest:['neck','neckBase','chestCirc','underBust','waist','highHip','hips'],arm:['upperArmTop','bicep','forearm','wrist'],leg:['thigh','knee','calf','ankle']};
export function measurementFields(profile,group){
 const fields=baseMeasurementFields(profile,group);
 const keys=shapeKeys[group]??shapeKeys[group.slice(0,3)];
 return fields.flatMap(f=>keys.includes(f.key)?[f,{key:'shape-'+f.key,label:f.label+' · szerokość/głębokość (%)',value:profile.avatar.shapes?.[group]?.[f.key]??100,min:60,max:160}]:[f]);
}
export function setMeasurement(profile,group,key,value){
  const field=measurementFields(profile,group).find(f=>f.key===key);
  if(!field||!Number.isFinite(value)||value<field.min||value>field.max)throw Error('Wymiar poza zakresem.');
  if(key.startsWith('shape-')){profile.avatar.shapes??={};profile.avatar.shapes[group]??={};profile.avatar.shapes[group][key.slice(6)]=value;return;}
  if(group==='head'){
    profile.avatar.headMeasured=true;
    if(key==='height')profile.head.dimensions[1]=value;
    else if(key==='circ')profile.head.dimensions=resizeHeadCircumference(profile.head.dimensions,value);
    else profile.head.details[key]=value;
  }else if(group==='chest'){
    if(key==='length')profile.chest.dimensions[1]=value;
    else profile.chest.details[key]=value;
  }else{
    const kind=group.slice(0,3),values=limbValues(profile,kind,group.at(-1));
    const patch={};
    if(key==='total'){
      const keys=kind==='arm'?['upperArmLength','forearmLength']:['thighLength','lowerLegLength'];
      const locked=keys.filter(k=>profile.avatar.locks?.[group+'.'+k]);
      if(locked.length===2)throw Error('Oba segmenty są zablokowane.');
      const fixed=locked.reduce((n,k)=>n+values[k],0);
      const ratio=(value-fixed)/(values[keys[0]]+values[keys[1]]-fixed);
      for(const k of keys){
        patch[k]=locked.includes(k)?values[k]:values[k]*ratio;
        if(patch[k]<LIMB_FIELDS[k].min||patch[k]>LIMB_FIELDS[k].max)throw Error('Łączna długość przekracza zakres segmentów.');
      }
    }else patch[key]=value;
    profile.avatar.limbs??={};
    profile.avatar.limbs[group]={...profile.avatar.limbs[group],...patch};
  }
}
export function mountMeasurements({getProfile,changed}){
  const $=id=>document.getElementById(id),panel=$('measurePanel'),select=$('measureTarget');
  for(const [key,label] of Object.entries(MEASUREMENT_GROUPS))select.add(new Option(label,key));
  let rendered='';
  function refresh(){
    if(panel.hidden)return;
    const group=select.value,fields=measurementFields(getProfile(),group),container=$('personalFields');
    if(rendered!==group){
      container.replaceChildren();
      for(const field of fields){
        const label=document.createElement('label');label.textContent=field.label;
        const input=document.createElement('input');input.type='number';input.step='.1';input.min=field.min;input.max=field.max;
        input.id='personal-'+field.key;
        input.onchange=()=>{
          try{setMeasurement(getProfile(),group,field.key,input.valueAsNumber);$('measureError').textContent='';changed();}
          catch(error){$('measureError').textContent=error.message;refresh();}
        };
        label.append(input);
        if(['upperArmLength','forearmLength','thighLength','lowerLegLength'].includes(field.key)){
          const lockLabel=document.createElement('span');lockLabel.className='measurement-lock';
          const lock=document.createElement('input');lock.type='checkbox';lock.id='lock-'+field.key;
          lock.onchange=()=>{getProfile().avatar.locks??={};getProfile().avatar.locks[group+'.'+field.key]=lock.checked;changed();};
          lockLabel.append(lock,document.createTextNode('Blokuj przy zmianie sumy'));label.append(lockLabel);
        }
        container.append(label);
      }
      rendered=group;
    }
    for(const field of fields){$('personal-'+field.key).value=Number(field.value.toFixed(1));const lock=$('lock-'+field.key);if(lock)lock.checked=!!getProfile().avatar.locks?.[group+'.'+field.key];}
  }
  $('editMeasurements').onclick=()=>{panel.hidden=!panel.hidden;refresh();};
  $('closeMeasurements').onclick=()=>panel.hidden=true;
  select.onchange=()=>{$('measureError').textContent='';refresh();};
  panel.addEventListener('keydown',e=>{if(e.key==='Escape'){panel.hidden=true;$('editMeasurements').focus();}});
  return refresh;
}
