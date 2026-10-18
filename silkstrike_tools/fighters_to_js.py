#!/usr/bin/env python3
import re, json, sys
src=open(sys.argv[1],encoding='utf-8').read()
def hexes(s):
    return {k: v for k,v in re.findall(r'(\w+Color): (?:Roster\.rgb\(0x([0-9A-Fa-f]{6})\)|nil)', s)}
def look(block):
    L={}
    m=re.search(r'build: \.(\w+)',block); L['build']=m.group(1)
    L['height']=float(re.search(r'height: ([\d.]+)',block).group(1))
    for k,v in re.findall(r'(skinColor|primaryColor|secondaryColor|glowColor|hairColor): Roster\.rgb\(0x([0-9A-Fa-f]{6})\)',block):
        L[k.replace('Color','')]='#'+v
    L['metal']=float(re.search(r'metalness: ([\d.]+)',block).group(1))
    L['rough']=float(re.search(r'roughness: ([\d.]+)',block).group(1))
    L['mask']='hasMask: true' in block
    L['eyes']=re.search(r'eyeStyle: \.(\w+)',block).group(1)
    acc=re.search(r'accessories: \[(.*?)\]',block,re.S).group(1)
    L['acc']=re.findall(r'\.(\w+)',acc)
    return L
def strf(k,b):
    m=re.search(k+r': "((?:[^"\\]|\\.)*)"',b); return m.group(1) if m else ''
out={'fighters':{},'cast':{}}
for m in re.finditer(r'private static func (\w+)Def\(\) -> FighterDef \{(.*?)\n    \}\n',src,re.S):
    b=m.group(2); fid=m.group(1)
    lk=look(re.search(r'FighterLook\((.*?)\n        \)',b,re.S).group(1))
    st=re.search(r'FighterStats\(maxHealth: ([\d.]+), walkSpeed: ([\d.]+), power: ([\d.]+), defense: ([\d.]+), jumpVelocity: ([\d.]+)\)',b)
    sp=[]
    for s in re.finditer(r'SpecialMoveDef\(name: "([^"]+)", kind: \.(\w+), damage: ([\d.]+), cooldown: ([\d.]+),\s*range: ([\d.]+), color: Roster\.rgb\(0x([0-9A-Fa-f]{6})\), sound: \.(\w+)\)',b):
        sp.append({'name':s.group(1),'kind':s.group(2),'damage':float(s.group(3)),'cooldown':float(s.group(4)),'range':float(s.group(5)),'color':'#'+s.group(6),'sound':s.group(7)})
    ex=re.search(r'ExecutionDef\(\s*name: "([^"]+)",\s*kind: \.(\w+)',b)
    fd=b[b.index('return FighterDef('):]
    vp=re.search(r'voicePitch: ([\d.]+)',fd).group(1); vr=re.search(r'voiceRate: ([\d.]+)',fd).group(1)
    out['fighters'][fid]={'id':fid,'name':strf('name',fd),'realName':strf('realName',fd),'title':strf('title',fd),'bio':strf('bio',fd),
        'look':lk,'stats':{'hp':float(st.group(1)),'walk':float(st.group(2)),'power':float(st.group(3)),'defense':float(st.group(4)),'jump':float(st.group(5))},
        'specials':sp,'exec':{'name':ex.group(1),'kind':ex.group(2)},'brutal':strf('brutalName',fd),'intro':strf('introQuote',fd),'win':strf('winQuote',fd),
        'pitch':float(vp),'rate':float(vr)}
for name in ['heroDarkSuitLook','lenaLook','morgrimLook','civilianLook']:
    m=re.search(r'static let '+name+r': FighterLook = FighterLook\((.*?)\n    \)',src,re.S)
    if m: out['cast'][name]=look(m.group(1))
print('fighters',list(out['fighters']),'cast',list(out['cast']),file=sys.stderr)
print('const ROSTER = '+json.dumps(out,ensure_ascii=False)+';')
