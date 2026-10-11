"""Behavioural comparison of the six harnesses on the SWE-bench run.

Uses the final scored row per (task, harness) from results/swebench/summary_tokens.csv
(psf__requests-2317 excluded) and the per-run artifacts in results/swebench/runs/.
Writes results/swebench/why_harnesses.json and prints a summary.
"""
import csv, glob, json, os, re, statistics as st, collections

R = 'results/swebench'
HS = ['cursor', 'swe_agent', 'claude_code', 'mini_swe_agent', 'opencode', 'aider']
TEST = re.compile(r'pytest|runtests\.py|\btox\b|-m unittest|manage\.py test|bin/test|unittest')
REPRO = re.compile(r'(^|[;&|\s])python3?\s+(-c|-\s|/tmp/|\S*repro|\S*test_\S*\.py|<<|-\s*<<)|python3? - <<|python3? -c')
EDITCMD = re.compile(r'sed -i|str_replace_editor (str_replace|create|insert)|cat >\s*/testbed|> /testbed/\S+\.py|\.write_text\(|open\([^)]*[\'"]w[\'"]|patch -p|git apply')

rows = {}
for r in csv.DictReader(open(f'{R}/summary_tokens.csv')):
    if r['instance_id'] == 'psf__requests-2317' or r['harness'] == 'gold':
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
    base = f'{R}/runs/{iid}/{h}'
    if h == 'cursor':
        p = f'{base}/stdout.txt'
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
    if h == 'swe_agent':
        f = glob.glob(f'{base}/out/*/*.traj')
        if not f:
            return None, 0
        for s in json.load(open(f[0]))['trajectory']:
            out.append(('shell', s.get('action') or ''))
        return out, 0
    if h == 'mini_swe_agent':
        f = glob.glob(f'{base}/out/*/*.traj.json')
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
    for h in HS:
        r = rows.get((iid, h))
        if not r:
            continue
        cs = calls(iid, h)
        rr = res.get((iid, h), {})
        acts, think = actions(iid, h)
        rec = dict(iid=iid, solved=r['resolved'] == 'True', calls=len(cs) or int(float(r['calls'] or 0)),
                   patch=rr.get('patch_lines') or 0, files=rr.get('files_changed') or 0,
                   first_prompt=cs[0]['prompt'] if cs else None, max_prompt=max((c['prompt'] for c in cs), default=None),
                   out_tok=sum(c['output'] for c in cs), wall=float(r['wall_s'] or 0), think=think)
        if acts is not None:
            kinds = [classify(k, t) for k, t in acts]
            rec['n_actions'] = len(kinds)
            fe = kinds.index('edit') if 'edit' in kinds else None
            rec['before_edit'] = fe if fe is not None else len(kinds)
            after = kinds[fe + 1:] if fe is not None else []
            rec['tested_after_edit'] = 'test' in after
            rec['checked_after_edit'] = ('test' in after) or ('run' in after)
            rec['repro_before_edit'] = ('run' in kinds[:fe]) if fe is not None else False
        if h == 'claude_code':
            try:
                d = json.loads(open(f'{R}/runs/{iid}/{h}/stdout.txt').read().splitlines()[0])
                rec['n_actions'] = d.get('num_turns')
                rec['think_tok'] = d['usage'].get('output_tokens_details', {}).get('thinking_tokens', 0)
            except Exception:
                pass
        if h == 'aider':
            s = open(f'{R}/runs/{iid}/{h}/stdout.txt', errors='ignore').read()
            rec['edit_fail'] = bool(re.search(r'SearchReplaceNoExactMatch|failed to match|did not match|Only \d+ reflections', s))
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
    if h == 'cursor':
        s['think_chars_med'] = med([r['think'] for r in rs])
        s['think_runs'] = sum(r['think'] > 0 for r in rs)
    if h == 'claude_code':
        s['turns_med'] = med([r['n_actions'] for r in rs if r.get('n_actions')])
        s['think_tok_med'] = med([r.get('think_tok', 0) for r in rs])
    if h == 'aider':
        s['edit_fail_runs'] = sum(r.get('edit_fail', False) for r in rs)
        s['edit_fail_solved'] = sum(r.get('edit_fail', False) and r['solved'] for r in rs)
    summ[h] = s

solved = {h: {r['iid'] for r in rs if r['solved']} for h, rs in per.items()}
only = {h: sorted(solved[h] - set().union(*[solved[o] for o in solved if o != h])) for h in solved}
missed_by_one = {h: sorted(set.intersection(*[solved[o] for o in solved if o != h]) - solved[h]) for h in solved}
out = dict(summary=summ, only_solved_by=only, missed_only_by=missed_by_one,
           runs={h: rs for h, rs in per.items()})
json.dump(out, open(f'{R}/why_harnesses.json', 'w'), indent=1)
for h, s in summ.items():
    print(h, s)
print('only', only)
print('missed_only_by', missed_by_one)
