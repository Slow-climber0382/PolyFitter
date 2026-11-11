"""Build ForgeFit's compact CC0 mesh asset from the pinned MakeHuman files."""
import argparse
import base64
import json
import struct
from pathlib import Path

REVISION = 'a8bc2d54ff0ac92e78ff71431b1023eda42bf482'
POSE_BONES = ['root', 'head'] + [
    f'{bone}.{side}' for side in ('L','R')
    for bone in ('upperarm01','lowerarm01','upperleg01','lowerleg01','foot')
]
TARGETS = {
    'male':'caucasian-male-young.target',
    'female':'caucasian-female-young.target',
    'noseProjection':'nose-scale-depth-incr.target',
    'noseWidth':'nose-scale-horiz-incr.target',
    'noseLength':'nose-scale-vert-incr.target',
    'noseHeight':'nose-trans-up.target',
}
REGIONS = ['chest','head','neck','waist','pelvis'] + [
    f'{region}.{side}' for side in ('L','R')
    for region in ('upperarm','forearm','hand','thigh','shin','foot')
]

def flatten(rows):
    return [value for row in rows for value in row]

def encode(fmt, values):
    return base64.b64encode(struct.pack('<'+fmt*len(values),*values)).decode()

def load_obj(path):
    vertices, triangles = [], []
    group = ''
    for line in path.read_text().splitlines():
        words = line.split()
        if not words:
            continue
        if words[0] == 'v':
            vertices.append(tuple(map(float, words[1:4])))
        elif words[0] == 'g':
            group = words[1]
        elif words[0] == 'f' and group in {'body','helper-l-eye','helper-r-eye'}:
            face = [int(v.split('/')[0])-1 for v in words[1:]]
            triangles.extend((face[0],face[i],face[i+1]) for i in range(1,len(face)-1))
    return vertices, triangles

def load_target(path):
    entries = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            index, *offset = line.split()
            entries[int(index)] = tuple(map(float,offset))
    return entries

def nearest_bone(name, bones):
    while name not in POSE_BONES:
        name = bones.get(name, {}).get('parent') or 'root'
    return name

def anatomical_region(name, point):
    x,y,_ = point
    side = 'L' if x>=0 else 'R'
    if y >= 6.12:
        return 'head'
    if y >= 5.74 and abs(x)<.63:
        return 'neck'
    if name.endswith(('.L','.R')):
        if name.startswith(('finger','wrist','hand','metacarpal')):
            return f'hand.{side}'
        if name.startswith('lowerarm'):
            return f'forearm.{side}'
        if name.startswith(('upperarm','shoulder')):
            return f'upperarm.{side}'
        if name.startswith(('foot','toe')):
            return f'foot.{side}'
        if name.startswith('lowerleg'):
            return f'shin.{side}'
        if name.startswith('upperleg') and y<.2:
            return f'thigh.{side}'
    if y<1.3:
        return 'pelvis'
    if y<3:
        return 'waist'
    return 'chest'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    vertices,triangles=load_obj(args.input/'base.obj')
    skeleton=json.loads((args.input/'default.mhskel').read_text())
    weights=json.loads((args.input/'default_weights.mhw').read_text())
    assert skeleton['license']==weights['license']=='CC0'
    bones=skeleton['bones']
    used=sorted(set(flatten(triangles)))
    indices={index:local for local,index in enumerate(used)}
    skin=[{} for _ in used]
    dominant=[(0,'root') for _ in used]
    for name,assignments in weights['weights'].items():
        target=POSE_BONES.index(nearest_bone(name,bones))
        for index,weight in assignments:
            if index not in indices:
                continue
            local=indices[index]
            skin[local][target]=skin[local].get(target,0)+weight
            if weight>dominant[local][0]:
                dominant[local]=(weight,name)
    joints=[]
    for name in POSE_BONES:
        bone=bones[name]
        points=[vertices[i] for i in skeleton['joints'][bone['head']]]
        center=[sum(p[axis] for p in points)/len(points) for axis in range(3)]
        parent=bone['parent']
        joints.append([name,POSE_BONES.index(nearest_bone(parent,bones)) if parent else -1,*center])
    skin_indices,skin_weights=[],[]
    for row in skin:
        top=sorted(row.items(),key=lambda item:-item[1])[:4] or [(0,1)]
        total=sum(w for _,w in top)
        skin_indices.extend([b for b,_ in top]+[0]*(4-len(top)))
        skin_weights.extend([w/total for _,w in top]+[0]*(4-len(top)))
    regions=[REGIONS.index(anatomical_region(dominant[i][1],vertices[v])) for i,v in enumerate(used)]
    face_regions=[]
    for a,b,c in triangles:
        choices=[regions[indices[i]] for i in (a,b,c)]
        face_regions.append(max(choices,key=choices.count))
    target_data={}
    for name,file in TARGETS.items():
        target=load_target(args.input/file)
        pairs=[(indices[i],xyz) for i,xyz in target.items() if i in indices]
        target_data[name]={
            'indices':encode('H',[i for i,_ in pairs]),
            'values':encode('f',flatten([v for _,v in pairs])),
        }
    data={
        'revision':REVISION,
        'vertices':encode('f',flatten([vertices[i] for i in used])),
        'faces':encode('H',[indices[i] for i in flatten(triangles)]),
        'faceRegions':encode('B',face_regions),
        'vertexRegions':encode('B',regions),
        'skinIndices':encode('B',skin_indices),
        'skinWeights':encode('f',skin_weights),
        'regions':REGIONS,'joints':joints,'targets':target_data,
    }
    args.output.write_text('// Generated from MakeHuman CC0 assets. See ASSETS.md.\nexport default '+json.dumps(data,separators=(',',':'))+';\n')

if __name__=='__main__':
    main()
