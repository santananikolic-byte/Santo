#!/usr/bin/env python3
"""Wandelt Data/Story.swift + Kapitel in JSON für die Web-Version um."""
import re, json, sys
src = open(sys.argv[1], encoding='utf-8').read()

def split_args(s):
    out=[];d=0;cur='';q=False
    for ch in s:
        if ch=='"' : q=not q
        if not q:
            if ch in '([': d+=1
            elif ch in ')]': d-=1
            elif ch==',' and d==0:
                out.append(cur.strip()); cur=''; continue
        cur+=ch
    if cur.strip(): out.append(cur.strip())
    return out

def call_body(s, start):
    # s[start] == '('
    d=0;q=False
    for i in range(start,len(s)):
        ch=s[i]
        if ch=='"' and s[i-1]!='\\': q=not q
        if q: continue
        if ch=='(': d+=1
        elif ch==')':
            d-=1
            if d==0: return s[start+1:i], i
    raise ValueError

def vec(s):
    m=re.match(r'v\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)', s.strip())
    return [float(m.group(1)),float(m.group(2)),float(m.group(3))] if m else None

def cast(s):
    s=s.strip()
    if s in ('kai',): return 'silkstrike'
    if s=='dark': return 'darksuit'
    if s=='nil': return None
    m=re.match(r'\.fighter\(\.(\w+)\)', s) or re.match(r'CastMember\.fighter\(\.(\w+)\)', s)
    if m: return m.group(1)
    m=re.match(r'(?:CastMember)?\.(\w+)', s)
    if m: return {'heroDarkSuit':'darksuit'}.get(m.group(1), m.group(1))
    return s

def parse_cam(expr):
    expr=expr.strip()
    presets={'overLeft':'overLeft','overRight':'overRight','twoShot':'twoShot'}
    m=re.match(r'(overLeft|overRight|twoShot)\((.*)\)$', expr, re.S)
    if m:
        a=split_args(m.group(2)); fov=None
        for x in a:
            if x.startswith('fov:'): fov=float(x.split(':')[1])
        return {'preset':m.group(1),'fov':fov}
    m=re.match(r'heroLow\(([-\d.]+)\)$', expr)
    if m: return {'preset':'heroLow','x':float(m.group(1))}
    m=re.match(r'cam\((.*)\)$', expr, re.S)
    a=split_args(m.group(1))
    c={'from':vec(a[0]),'to':vec(a[1])}
    for x in a[2:]:
        k,v=x.split(':',1); k=k.strip(); v=v.strip()
        if k in('look','lookTo'): c[k]=vec(v)
        elif k in('fov','fovTo','focus'): c[k]=float(v)
        elif k=='easing': c[k]=v.lstrip('.')
    return c

def parse_event(e):
    e=e.strip()
    m=re.match(r'\.clip\(actor: "(\w+)", \.(\w+)\)', e)
    if m: return ['clip',m.group(1),m.group(2)]
    m=re.match(r'\.(show|hide)\(actor: "(\w+)"\)', e)
    if m: return [m.group(1),m.group(2)]
    m=re.match(r'\.setCast\(actor: "(\w+)", (.+)\)$', e)
    if m: return ['setCast',m.group(1),cast(m.group(2))]
    m=re.match(r'\.sound\(\.(\w+)\)', e)
    if m: return ['sound',m.group(1)]
    m=re.match(r'\.music\(\.(\w+)\)', e)
    if m: return ['music',m.group(1)]
    m=re.match(r'\.shake\(([-\d.]+)\)', e)
    if m: return ['shake',float(m.group(1))]
    m=re.match(r'\.slowMotion\(([-\d.]+)\)', e)
    if m: return ['slow',float(m.group(1))]
    m=re.match(r'\.flash\((.+)\)$', e)
    if m:
        c=m.group(1)
        mm=re.search(r'red: ([\d.]+), green: ([\d.]+), blue: ([\d.]+)', c)
        col=[float(mm.group(1)),float(mm.group(2)),float(mm.group(3))] if mm else [1,1,1]
        return ['flash',col]
    m=re.match(r'\.effect\(\.(\w+), position: (v\([^)]*\))\)', e)
    if m: return ['effect',m.group(1),vec(m.group(2))]
    return ['unknown',e]

cuts={}
for fm in re.finditer(r'private static func (\w+)\(\) -> CutsceneDef \{(.*?)\n    \}\n', src, re.S):
    body=fm.group(2)
    lets={}
    for lm in re.finditer(r'let (\w+) = (CastMember\.\w+)', body):
        lets[lm.group(1)]=cast(lm.group(2))
    shots=[]
    for sm in re.finditer(r'let s\d+: Shot = shot\(', body):
        inner,_=call_body(body, sm.end()-1)
        args=split_args(inner)
        camx=parse_cam(args[0])
        lines=[]
        lm=re.match(r'\[(.*)\]$', args[1].strip(), re.S)
        for L in re.finditer(r'L\(([^,]+), "((?:[^"\\]|\\.)*)"\)', lm.group(1)):
            cs=L.group(1).strip()
            lines.append([lets.get(cs, cast(cs)), L.group(2)])
        extra=1.0; events=[]
        for a in args[2:]:
            if a.startswith('extra:'): extra=float(a.split(':')[1])
            if a.startswith('events:'):
                ev=a.split(':',1)[1].strip()[1:-1]
                for em in re.finditer(r'at\(([\d.]+), ', ev):
                    st=em.end()-len(', ')-len(em.group(0))+len('at(')
                for part in split_args(ev):
                    pm=re.match(r'at\(([\d.]+),\s*(.*)\)$', part.strip(), re.S)
                    events.append([float(pm.group(1))]+parse_event(pm.group(2)))
        shots.append({'cam':camx,'lines':lines,'extra':extra,'events':events})
    dm=re.search(r'CutsceneDef\(id: "(\w+)", title: (nil|"[^"]*"), stage: \.(\w+)(?:\(\.(\w+)\))?, timeOfDay: \.(\w+), music: \.(\w+),', body)
    actors=[]
    for am in re.finditer(r'actor\("(\w+)", ([^,]+(?:\([^)]*\))?), ([-\d.]+), ([-\d.]+), yaw: ([-\d.]+), \.(\w+)\)', body):
        cs=am.group(2).strip()
        actors.append({'key':am.group(1),'cast':lets.get(cs,cast(cs)),'x':float(am.group(3)),'z':float(am.group(4)),'yaw':float(am.group(5)),'clip':am.group(6)})
    cid=dm.group(1)
    cuts[cid]={'id':cid,'title':None if dm.group(2)=='nil' else dm.group(2).strip('"'),
               'stage':dm.group(3),'arena':dm.group(4),'tod':dm.group(5),'music':dm.group(6),
               'actors':actors,'shots':shots}
chapters=[]
for cm in re.finditer(r'ChapterDef\((.*?)timeOfDay: \.(\w+)\)', src, re.S):
    a=cm.group(1)
    def g(k):
        m=re.search(k+r': "((?:[^"\\]|\\.)*)"', a)
        if m: return m.group(1)
        return re.search(k+r': ([^,]+),', a).group(1).strip()
    chapters.append({'number':int(g('number')),'title':g('title').strip('"'),'subtitle':g('subtitle').strip('"'),
        'intro':g('introCutscene').strip('"'),'objectiveText':g('objectiveText').strip('"'),'objective':g('objective').lstrip('.'),
        'opponent':g('opponent').lstrip('.'),'arena':g('arena').lstrip('.'),'dark':g('heroDarkSuit')=='true',
        'pre':g('preFightCutscene').strip('"'),'outro':g('outroCutscene').strip('"'),'ai':float(g('aiLevel')),'tod':cm.group(2)})
credits=re.search(r'static let creditsLines: \[String\] = \[(.*?)\]', src, re.S).group(1)
credits=re.findall(r'"((?:[^"\\]|\\.)*)"', credits)
unk=[e for c in cuts.values() for s in c['shots'] for e in s['events'] if e[1]=='unknown']
print('cutscenes',len(cuts),'chapters',len(chapters),'unknown events',unk[:5], file=sys.stderr)
print('const STORY = '+json.dumps({'chapters':chapters,'cutscenes':cuts,'credits':credits},ensure_ascii=False)+';')
