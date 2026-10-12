import json,re,glob,os,collections,sys
R=os.path.expanduser('~/context-shaping/results/swebench')
H=["claude_code_nothink","cursor_nothink","opencode_nothink","swe_agent_nothink","mini_swe_agent_nothink","claude_code_nothink2","cursor_nothink2"]
last={}
for l in open(R+'/results.jsonl'):
    r=json.loads(l)
    if r['harness'] in H and not r.get('excluded'): last[(r['instance_id'],r['harness'])]=r
tasks=sorted({t for t,h in last})
TEST=re.compile(r'pytest|runtests\.py|unittest|bin/test|tox\b|setup\.py test')
FAIL=re.compile(r'Traceback|\bFAIL|FAILED|Error:|\berror\b|AssertionError|failed',re.I)
def classify_bash(cmd):
    c=cmd
    if re.search(r'sed -i|perl -pi|git apply|patch -p|\bed\b -s',c): return 'E'
    if re.search(r"cat\s*>+\s*(?!/tmp)\S+\.py|>\s*(?!/tmp|/dev)[\w/.-]+\.py\b",c) and '/tmp' not in c.split('>')[1][:8]: return 'E'
    if re.search(r"open\([^)]*['\"]w['\"]|write_text\(|\.write\(",c) and re.search(r'/testbed|\.py',c) and not re.search(r"open\(['\"]/tmp",c): return 'E'
    if TEST.search(c): return 'T'
    if re.search(r'\bpython3?\b',c) and not re.search(r'^\s*(cd [^&]*&&\s*)?(grep|sed -n|cat|ls|find)\b',c): return 'X'
    return 'R'
def ev_swe(t):
    f=glob.glob(f'{R}/runs/{t}/swe_agent_nothink/out/{t}/{t}.traj')
    if not f: return None
    ev=[];lint=0
    for s in json.load(open(f[0]))['trajectory']:
        a=s['action'].strip();o=s['observation'] or ''
        if not a: continue
        if a.startswith('submit'): ev.append(('S',a,o));continue
        if a.startswith('str_replace_editor'):
            k='E' if re.match(r'str_replace_editor (create|str_replace|insert|undo_edit)',a) else 'R'
            if k=='E' and re.search(r'syntax error|flake8|did not appear verbatim|No replacement was performed',o,re.I): lint+=1; k='Ex'
            ev.append((k,a,o));continue
        ev.append((classify_bash(a),a,o))
    return ev,lint
def ev_mini(t):
    f=glob.glob(f'{R}/runs/{t}/mini_swe_agent_nothink/out/{t}/{t}.traj.json')
    if not f: return None
    m=json.load(open(f[0]))['messages'];ev=[]
    for i,x in enumerate(m):
        for tc in (x.get('tool_calls') or []):
            try: c=json.loads(tc['function']['arguments']).get('command','')
            except: c=''
            o=''
            for y in m[i+1:i+4]:
                if y['role']=='tool': o=str(y['content']);break
            ev.append((classify_bash(c),c,o))
    return ev,0
def ev_oc(t):
    f=f'{R}/runs/{t}/opencode_nothink/stderr.txt'
    if not os.path.exists(f): return None
    s=re.sub(r'\x1b\[[0-9;]*m','',open(f,errors='ignore').read())
    ev=[];cur=None
    for line in s.splitlines():
        m=re.match(r'^(\$|←|→|✱|✗) (.*)',line)
        if m:
            if cur: ev.append(cur)
            sym,rest=m.groups()
            k={'$':None,'←':'E','→':'R','✱':'R','✗':'Ex'}[sym]
            cur=[k or classify_bash(rest),rest,'']
        elif cur: cur[2]+=line+'\n'
    if cur: ev.append(cur)
    return [tuple(e) for e in ev],sum(e[0]=='Ex' for e in ev)
def ev_cur(t,h='cursor_nothink'):
    f=f'{R}/runs/{t}/{h}/stdout.txt'
    if not os.path.exists(f): return None
    raw=open(f,errors='ignore').read();trunc=h=='cursor_nothink' and len(raw)>=199000
    ev=[];res={}
    for l in raw.splitlines():
        try: d=json.loads(l)
        except: continue
        if d.get('type')!='tool_call': continue
        tc=d['tool_call'];k=list(tc)[0];a=tc[k].get('args',{})
        if d['subtype']=='started': continue
        o=json.dumps(tc[k].get('result',''))[:20000]
        if k=='shellToolCall': ev.append((classify_bash(a.get('command','')),a.get('command',''),o))
        elif k in('editToolCall','writeToolCall','searchReplaceToolCall','applyPatchToolCall'): ev.append(('E',json.dumps(a)[:200],o))
        else: ev.append(('R',k,o))
    return ev,0,trunc
def ev_cc(t,h='claude_code_nothink2'):
    # Claude Code --output-format stream-json --verbose: assistant tool_use blocks, results in the next user message
    f=f'{R}/runs/{t}/{h}/stdout.txt'
    if not os.path.exists(f): return None
    calls=[];res={}
    for l in open(f,errors='ignore'):
        try: d=json.loads(l)
        except: continue
        for c in (d.get('message') or {}).get('content') or []:
            if not isinstance(c,dict): continue
            if d.get('type')=='assistant' and c.get('type')=='tool_use': calls.append(c)
            elif d.get('type')=='user' and c.get('type')=='tool_result':
                o=c.get('content');res[c.get('tool_use_id')]=o if isinstance(o,str) else json.dumps(o)
    ev=[]
    for c in calls:
        n,a,o=c.get('name',''),c.get('input') or {},res.get(c.get('id'),'')[:20000]
        if n=='Bash': ev.append((classify_bash(a.get('command','')),a.get('command',''),o))
        elif n in('Edit','MultiEdit','Write','NotebookEdit'):
            bad=re.search(r'String to replace not found|<tool_use_error>',o or '')
            ev.append(('Ex' if bad else 'E',json.dumps(a)[:200],o))
        else: ev.append(('R',n,o))
    return ev,sum(e[0]=='Ex' for e in ev)
def feats(ev):
    k=[e[0] for e in ev]
    fe=next((i for i,x in enumerate(k) if x=='E'),None)
    run=lambda x:x in('T','X')
    repro_first= fe is not None and any(run(x) for x in k[:fe])
    cyc=0;revise=0;fails_after=0;tested_after=False
    if fe is not None:
        prev='E'
        for i in range(fe,len(ev)):
            x=k[i]
            if run(x):
                tested_after=True
                if prev=='E': cyc+=1
                prev='T'
                if FAIL.search(ev[i][2] or ''):
                    fails_after+=1
                    if 'E' in k[i+1:]: revise+=1
            elif x=='E': prev='E'
    return dict(n=len(ev),edits=k.count('E'),runs=sum(run(x) for x in k),suite=k.count('T'),repro_first=repro_first,tested_after=tested_after,cycles=cyc,revise=revise>0,fail_checks=fails_after,noedit=fe is None)
out={}
for t in tasks:
    for h,fn in [('swe_agent_nothink',ev_swe),('mini_swe_agent_nothink',ev_mini),('opencode_nothink',ev_oc),('cursor_nothink',ev_cur),
                 ('cursor_nothink2',lambda t:ev_cur(t,'cursor_nothink2')),('claude_code_nothink2',ev_cc)]:
        r=fn(t)
        if r is None: continue
        f=feats(r[0]);f['lint']=r[1];f['trunc']=r[2] if len(r)>2 else False
        f['resolved']=bool(last.get((t,h),{}).get('resolved'));out[(t,h)]=(f,r[0])
    # claude code: only turns
    p=f'{R}/runs/{t}/claude_code_nothink/stdout.txt'
    try:
        d=json.loads(open(p).read().strip().splitlines()[-1]);out[(t,'claude_code_nothink')]=(dict(turns=d.get('num_turns'),result=d.get('result','')[:400],resolved=bool(last.get((t,'claude_code_nothink'),{}).get('resolved'))),[])
    except Exception as e: pass
import pickle;pickle.dump((tasks,last,{k:v for k,v in out.items()}),open('/workspace/why/out.pkl','wb'))
print('ok',len(out))
# behavior summary per harness (share of runs; 'checked its fix' = ran code after its first edit)
for h in H:
    fs=[v[0] for (t,hh),v in out.items() if hh==h and 'tested_after' in v[0]]
    if not fs: continue
    ed=[f for f in fs if not f['noedit']]
    pct=lambda k,xs:f"{100*sum(bool(f[k]) for f in xs)/max(len(xs),1):.0f}%"
    print(f"{h:24s} n={len(fs):2d} checked_fix={pct('tested_after',ed)} (all runs {pct('tested_after',fs)}) revised_after_fail={pct('revise',ed)} "
          f"repro_first={pct('repro_first',ed)} median_steps={sorted(f['n'] for f in fs)[len(fs)//2]} truncated={sum(f['trunc'] for f in fs)}")
