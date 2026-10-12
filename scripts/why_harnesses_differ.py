"""Behavioural comparison of the six harnesses on the SWE-bench run.

Uses the final scored row per (task, harness) from results/swebench/summary_tokens.csv
(pinned 50-task subset; psf__requests-2317 replaced by psf__requests-1142),
plus the confound-free variants opencode_auto and cursor_nothink and the per-run artifacts in results/swebench/runs/.
Writes results/swebench/why_harnesses.json and prints a summary.
"""
import csv, glob, json, os, re, statistics as st, collections

R = 'results/swebench'
HS = ['cursor', 'swe_agent', 'claude_code', 'mini_swe_agent', 'opencode', 'aider']
VARIANTS = ['opencode_auto', 'cursor_nothink']
# Same settings (2026-10-11): every harness on claude-haiku-5-5 with thinking off. Cursor uses its "No Thinking"
# model id, the proxied five ran with the proxy forcing thinking={"type":"disabled"}; OpenCode with auto-approve.
SAME = {'cursor': 'cursor_nothink', 'swe_agent': 'swe_agent_nothink', 'claude_code': 'claude_code_nothink',
        'mini_swe_agent': 'mini_swe_agent_nothink', 'opencode': 'opencode_nothink', 'aider': 'aider_nothink'}
VARIANTS += [v for v in SAME.values() if v not in VARIANTS]
base = lambda h: h.replace('_nothink', '').replace('_auto', '')
SUBSET = {i['instance_id'] for i in json.load(open(f'{R}/subset.json'))['instances']}
TEST = re.compile(r'pytest|runtests\.py|\btox\b|-m unittest|manage\.py test|bin/test|unittest')
REPRO = re.compile(r'(^|[;&|\s])python3?\s+(-c|-\s|/tmp/|\S*repro|\S*test_\S*\.py|<<|-\s*<<)|python3? - <<|python3? -c')
EDITCMD = re.compile(r'sed -i|str_replace_editor (str_replace|create|insert)|cat >\s*/testbed|> /testbed/\S+\.py|\.write_text\(|open\([^)]*[\'"]w[\'"]|patch -p|git apply')

rows = {}
for r in csv.DictReader(open(f'{R}/summary_tokens.csv')):
    if r['instance_id'] not in SUBSET or r['harness'] == 'gold':
        continue
    rows[(r['instance_id'], r['harness'])] = r
res = {}
for l in open(f'{R}/results.jsonl'):
    d = json.loads(l)
    res[(d['instance_id'], d['harness'])] = d
TASKS = sorted({i for i, _ in rows})


def calls(iid, h):
    p = f'{R}/runs/{iid}/{h}/calls.jsonl'
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def actions(iid, h):
    """Ordered list of (kind, text) for harnesses with transcripts."""
    out = []
    rd = f'{R}/runs/{iid}/{h}'
    if h.startswith('cursor'):
        p = f'{rd}/stdout.txt'
        if not os.path.exists(p):
            return None, 0
        think = 0
        for l in open(p):
            try:
                d = json.loads(l)
            except Exception:
                continue
            if d.get('type') == 'thinking' and d.get('subtype') == 'delta':
                think += len(d.get('text') or '')
            if d.get('type') == 'tool_call' and d.get('subtype') == 'started':
                tc = d['tool_call']
                k = next(iter(tc))
                a = tc[k].get('args', {})
                if k == 'shellToolCall':
                    out.append(('shell', a.get('command', '')))
                elif k in ('editToolCall', 'writeToolCall', 'applyPatchToolCall', 'deleteToolCall'):
                    out.append(('edit', a.get('path', '')))
                elif k in ('readToolCall',):
                    out.append(('read', a.get('path', '')))
                else:
                    out.append(('search', k))
        return out, think
    if base(h) == 'swe_agent':
        f = glob.glob(f'{rd}/out/*/*.traj')
        if not f:
            return None, 0
        for s in json.load(open(f[0]))['trajectory']:
            out.append(('shell', s.get('action') or ''))
        return out, 0
    if base(h) == 'mini_swe_agent':
        f = glob.glob(f'{rd}/out/*/*.traj.json')
        if not f:
            return None, 0
        for m in json.load(open(f[0]))['messages']:
            for tc in m.get('tool_calls') or []:
                try:
                    out.append(('shell', json.loads(tc['function']['arguments']).get('command', '')))
                except Exception:
                    pass
        return out, 0
    return None, 0


def classify(kind, text):
    if kind == 'edit':
        return 'edit'
    if kind in ('read', 'search'):
        return 'read'
    if EDITCMD.search(text):
        return 'edit'
    if TEST.search(text):
        return 'test'
    if REPRO.search(text):
        return 'run'
    if text.strip() in ('submit',):
        return 'submit'
    return 'read'


per = collections.defaultdict(list)
for iid in TASKS:
    for h in HS + VARIANTS:
        r = rows.get((iid, h))
        if not r:
            continue
        cs = calls(iid, h)
        rr = res.get((iid, h), {})
        acts, think = actions(iid, h)
        rec = dict(iid=iid, solved=r['resolved'] == 'True', calls=len(cs) or int(float(r['calls'] or 0)),
                   patch=rr.get('patch_lines') or 0, files=rr.get('files_changed') or 0,
                   first_prompt=cs[0]['prompt'] if cs else None, max_prompt=max((c['prompt'] for c in cs), default=None),
                   out_tok=sum(c['output'] for c in cs), wall=float(r['wall_s'] or 0), think=think,
                   think_blocks=sum(c.get('think_blocks') or 0 for c in cs) if cs and 'think_blocks' in cs[0] else None)
        if acts is not None:
            kinds = [classify(k, t) for k, t in acts]
            rec['n_actions'] = len(kinds)
            fe = kinds.index('edit') if 'edit' in kinds else None
            rec['before_edit'] = fe if fe is not None else len(kinds)
            after = kinds[fe + 1:] if fe is not None else []
            rec['tested_after_edit'] = 'test' in after
            rec['checked_after_edit'] = ('test' in after) or ('run' in after)
            rec['repro_before_edit'] = ('run' in kinds[:fe]) if fe is not None else False
        if base(h) == 'claude_code':
            try:
                d = json.loads(open(f'{R}/runs/{iid}/{h}/stdout.txt').read().splitlines()[0])
                rec['n_actions'] = d.get('num_turns')
                rec['think_tok'] = d['usage'].get('output_tokens_details', {}).get('thinking_tokens', 0)
            except Exception:
                pass
        if base(h) == 'aider':
            s = open(f'{R}/runs/{iid}/{h}/stdout.txt', errors='ignore').read()
            rec['edit_fail'] = bool(re.search(r'SearchReplaceNoExactMatch|failed to match|did not match|Only \d+ reflections', s))
        if h.startswith('opencode'):
            e = f'{R}/runs/{iid}/{h}/stderr.txt'
            rec['perm_reject'] = os.path.exists(e) and 'rejected permission' in open(e, errors='ignore').read()
        per[h].append(rec)

summ = {}
med = lambda xs: round(st.median(xs), 1) if xs else None
pct = lambda xs: round(100 * sum(xs) / len(xs)) if xs else None
for h, rs in per.items():
    s = dict(n=len(rs), solved=sum(r['solved'] for r in rs),
             calls_med=med([r['calls'] for r in rs]),
             empty_patch=sum(r['patch'] == 0 for r in rs),
             patch_med_solved=med([r['patch'] for r in rs if r['solved']]),
             max_prompt_med=med([r['max_prompt'] for r in rs if r['max_prompt']]),
             out_tok_med=med([r['out_tok'] for r in rs]))
    if any('before_edit' in r for r in rs):
        t = [r for r in rs if 'before_edit' in r]
        s.update(n_traj=len(t), actions_med=med([r['n_actions'] for r in t]),
                 before_edit_med=med([r['before_edit'] for r in t]),
                 tested_after_edit=pct([r['tested_after_edit'] for r in t]),
                 checked_after_edit=pct([r['checked_after_edit'] for r in t]),
                 repro_before_edit=pct([r['repro_before_edit'] for r in t]),
                 solve_if_checked=pct([r['solved'] for r in t if r['checked_after_edit']]),
                 solve_if_not_checked=pct([r['solved'] for r in t if not r['checked_after_edit']]),
                 n_checked=sum(r['checked_after_edit'] for r in t))
    if h.startswith('opencode'):
        s['perm_reject_runs'] = sum(r.get('perm_reject', False) for r in rs)
    if h.startswith('cursor'):
        s['think_chars_med'] = med([r['think'] for r in rs])
        s['think_runs'] = sum(r['think'] > 0 for r in rs)
    tb = [r['think_blocks'] for r in rs if r.get('think_blocks') is not None]
    if tb:
        s['think_block_runs'] = sum(x > 0 for x in tb); s['think_logged_runs'] = len(tb)
    if base(h) == 'claude_code':
        s['turns_med'] = med([r['n_actions'] for r in rs if r.get('n_actions')])
        s['think_tok_med'] = med([r.get('think_tok', 0) for r in rs])
    if base(h) == 'aider':
        s['edit_fail_runs'] = sum(r.get('edit_fail', False) for r in rs)
        s['edit_fail_solved'] = sum(r.get('edit_fail', False) and r['solved'] for r in rs)
    summ[h] = s

solved = {h: {r['iid'] for r in rs if r['solved']} for h, rs in per.items() if h in HS}  # overlap among the original six
only = {h: sorted(solved[h] - set().union(*[solved[o] for o in solved if o != h])) for h in solved}
missed_by_one = {h: sorted(set.intersection(*[solved[o] for o in solved if o != h]) - solved[h]) for h in solved}
sv = {b: {r['iid'] for r in per[v] if r['solved']} for b, v in SAME.items() if v in per}
only_same = {h: sorted(sv[h] - set().union(*[sv[o] for o in sv if o != h])) for h in sv} if len(sv) > 1 else {}
all_same = sorted(set.intersection(*sv.values())) if sv else []
none_same = sorted(set(TASKS) - set().union(*sv.values())) if sv else []
out = dict(summary=summ, only_solved_by=only, missed_only_by=missed_by_one,
           same_settings=dict(map=SAME, only_solved_by=only_same, solved_by_all=len(all_same), solved_by_none=len(none_same)),
           runs={h: rs for h, rs in per.items()})
json.dump(out, open(f'{R}/why_harnesses.json', 'w'), indent=1)
for h, s in summ.items():
    print(h, s)
print('only', only)
print('missed_only_by', missed_by_one)
print('same_settings', out['same_settings'])
