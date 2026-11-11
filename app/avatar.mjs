// Measurement defaults are starting proportions. Explicit regional overrides
// remain in millimetres when stature or the base body type changes.
export const BODY_TYPES = {neutral:'Neutralny', male:'Męski', female:'Żeński'};
export const DEFAULT_STATURE = 1750;
const field = (label, min, max) => ({label,min,max});
export const DETAILS = {
  head:{
    jawWidth:field('Szerokość żuchwy',50,240),
    faceDepth:field('Wysunięcie twarzy względem środka',20,180),
    noseProjection:field('Wystawanie nosa od twarzy',0,100),
    noseWidth:field('Szerokość nosa',8,100),
    noseLength:field('Długość nosa',12,120),
    noseHeight:field('Położenie czubka nosa od brody',12,240),
    earSpan:field('Szerokość głowy z uszami',70,350),
    earHeight:field('Wysokość ucha',15,130),
    earDepth:field('Głębokość ucha',8,85),
    eyeSpacing:field('Rozstaw oczu',30,115),
    eyeHeight:field('Położenie oczu od brody',40,290),
    mouthWidth:field('Szerokość ust',20,115),
    chinDepth:field('Wysunięcie brody',0,95)
  },
  chest:{
    shoulders:field('Szerokość barków',150,750),
    singleShoulder:field('Długość jednego barku',40,350),
    armhole:field('Obwód pachy',120,1000),
    acrossChest:field('Szerokość między pachami z przodu',100,730),
    backWidth:field('Szerokość pleców',120,720),
    chestCirc:field('Obwód klatki / biustu',300,2400),
    highBust:field('Obwód nad biustem',300,2400),
    underBust:field('Obwód pod biustem',300,2400),
    waist:field('Obwód talii',300,2500),
    highHip:field('Obwód górnej linii bioder',300,2600),
    hips:field('Obwód bioder',320,2700),
    neck:field('Obwód szyi',160,750),
    neckLength:field('Długość szyi',20,150),
    neckBase:field('Obwód podstawy szyi',180,950),
    bustProjection:field('Wysunięcie biustu',0,190),
    breastSize:field('Wielkość biustu · %',50,180),
    breastHeight:field('Przesunięcie biustu w pionie',-80,80),
    buttSize:field('Wielkość pośladków · %',60,160),
    upperArmLength:field('Bark do łokcia',80,650),
    forearmLength:field('Łokieć do nadgarstka',70,550),
    upperArmTop:field('Obwód ramienia przy barku',100,1050),
    bicep:field('Obwód bicepsa',100,900),
    elbow:field('Obwód łokcia',90,650),
    forearm:field('Obwód przedramienia',80,700),
    wrist:field('Obwód nadgarstka',70,470),
    handLength:field('Długość dłoni',65,350),
    handWidth:field('Szerokość dłoni',35,180)
  },
  shin:{
    knee:field('Obwód kolana',120,900),
    calf:field('Obwód łydki',130,1000),
    ankle:field('Obwód kostki',100,670),
    thigh:field('Obwód uda',180,1500),
    thighLength:field('Długość uda',140,900),
    footLength:field('Długość stopy',100,440)
  }
};

export function ellipsePerimeter(width,depth){
  const a=width/2,b=depth/2;
  const q=((a-b)/(a+b))**2;
  return Math.PI*(a+b)*(1+3*q/(10+Math.sqrt(4-3*q)));
}
export function headCircumference(dimensions){
  return ellipsePerimeter(dimensions[0],dimensions[2]);
}
export function resizeHeadCircumference(dimensions,circumference){
  const factor=circumference/headCircumference(dimensions);
  return [dimensions[0]*factor,dimensions[1],dimensions[2]*factor];
}
export function detailValues(region,item,type){
  const [w,h,d]=item.dimensions;
  let values;
  if(region==='head'){
    values={jawWidth:w*.77,faceDepth:d*.43,noseProjection:w*.16,noseWidth:w*.23,noseLength:h*.22,
      noseHeight:h*.39,earSpan:w*1.12,earHeight:h*.28,earDepth:d*.16,
      eyeSpacing:w*.41,eyeHeight:h*.56,mouthWidth:w*.33,chinDepth:d*.135};
  }else if(region==='chest'){
    const chest=ellipsePerimeter(w,d);
    const proportions={neutral:[1.24,.80,1.02,0],male:[1.34,.84,.97,0],female:[1.13,.74,1.13,.17]};
    const [shoulders,waist,hips,bust]=proportions[type];
    values={shoulders:w*shoulders,singleShoulder:w*.39,armhole:w*1.18,acrossChest:w*.93,
      backWidth:w*.94,chestCirc:chest,
      highBust:chest*.94,underBust:chest*(type==='female'?.87:.93),waist:chest*waist,
      highHip:chest*(waist+hips)/2,hips:chest*hips,neck:w*1.04,neckLength:h*.073,neckBase:w*1.20,bustProjection:d*bust,breastSize:100,breastHeight:0,buttSize:100,
      upperArmLength:h*.55,forearmLength:h*.46,upperArmTop:w*.98,bicep:w*.89,elbow:w*.73,
      forearm:w*.75,wrist:w*.49,handLength:h*.36,handWidth:w*.25};
  }else{
    const calf=ellipsePerimeter(w,d);
    values={knee:calf*.87,calf,ankle:calf*.66,thigh:calf*1.56,thighLength:h*1.15,footLength:h*.70};
  }
  return Object.fromEntries(Object.entries(DETAILS[region]).map(([key,{min,max}])=>[
    key,item.details?.[key]??Math.round(Math.min(max,Math.max(min,values[key])))
  ]));
}

export function profileDetails(profile,region){
  const result=detailValues(region,profile[region],profile.avatar.type);
  if(region==='shin'&&profile.shin.details?.thighLength===undefined){
    const torso=detailValues('chest',profile.chest,profile.avatar.type);
    const available=profile.avatar.stature*.957-profile.head.dimensions[1]-torso.neckLength
      -profile.chest.dimensions[1]-profile.shin.dimensions[1];
    result.thighLength=Math.round(Math.max(140,Math.min(900,available)));
  }
  return result;
}

export const ARM_FIELDS=['upperArmLength','forearmLength','upperArmTop','bicep','elbow','forearm','wrist','handLength','handWidth'];
export const LEG_FIELDS=['thighLength','lowerLegLength','thigh','knee','calf','ankle','footLength'];
export const LIMB_FIELDS={...Object.fromEntries(ARM_FIELDS.map(k=>[k,DETAILS.chest[k]])),...DETAILS.shin,
  lowerLegLength:field('Kolano do kostki',120,750)};
export function limbValues(profile,kind,side){
  const values=profileDetails(profile,kind==='arm'?'chest':'shin');
  if(kind==='leg')values.lowerLegLength=profile.shin.dimensions[1];
  return {...values,...profile.avatar.limbs?.[kind+side]};
}
