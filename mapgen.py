"""
mapgen — build the Vikunja map HTML from live API data.

Fetches every project, task and relation from a Vikunja instance and renders a
single self-contained HTML page: a force-directed dependency graph, a leverage
panel ("what does this unblock, and how heavy is it"), a critical-path view, and
a full project/task tree.

Configuration (environment variables):
    VIKUNJA_URL    base URL of the instance (``/api/v1`` is appended if missing)
    VIKUNJA_TOKEN  API token (a read-only token is enough)

No secrets are stored in the code; the token is read from the environment.
"""
import os
import json
import html
import colorsys
import datetime
import urllib.request
import urllib.error


def _api():
    url = os.environ['VIKUNJA_URL'].rstrip('/')
    base = url if url.endswith('/api/v1') else url + '/api/v1'
    return base, os.environ['VIKUNJA_TOKEN']


def _call(path):
    base, token = _api()
    req = urllib.request.Request(
        base + path,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode())


def fetch():
    """Return (projects, tasks, edges) from the Vikunja API.

    edges is a list of (src_id, dst_id, kind) with kind in
    {'blocks', 'precedes', 'related'}; 'blocked'/'follows' are the reverse of
    'blocks'/'precedes' and are skipped to avoid duplicates.
    """
    projs = [p for p in _call('/projects?per_page=200') if p['id'] > 0]
    tasks = {}
    for p in projs:
        for t in _call(f"/projects/{p['id']}/tasks?per_page=250"):
            tasks[t['id']] = t
    edges = []
    for tid, t in tasks.items():
        rel = t.get('related_tasks') or {}
        for kind, lst in rel.items():
            for rt in (lst or []):
                oid = rt['id']
                if kind == 'blocking':
                    edges.append((tid, oid, 'blocks'))
                elif kind == 'precedes':
                    edges.append((tid, oid, 'precedes'))
                elif kind == 'related' and tid < oid:
                    edges.append((tid, oid, 'related'))
    return projs, list(tasks.values()), edges


def build(projs, tasks, edges):
    """Render the full HTML page from projects, tasks and edges."""
    pmap = {p['id']: p for p in projs}
    tmap = {t['id']: t for t in tasks}
    pos_ids = sorted(pmap)
    colors = {}
    for i, pid in enumerate(pos_ids):
        h = (i * 0.61803398875) % 1.0
        r, g, b = colorsys.hls_to_rgb(h, 0.55, 0.62)
        colors[pid] = '#%02x%02x%02x' % (int(r * 255), int(g * 255), int(b * 255))

    def short(t, n=42):
        s = t.strip()
        return s if len(s) <= n else s[:n - 1] + '…'

    # graph nodes = tasks that take part in at least one edge
    nodeids = set()
    for a, b, k in edges:
        nodeids.add(a); nodeids.add(b)
    gnodes = []
    meta = {}
    for tid in nodeids:
        t = tmap.get(tid)
        if not t:
            continue
        pid = t['project_id']
        gnodes.append({'id': tid, 'label': f"#{tid}",
            'title': f"#{tid} · {html.escape(t['title'])}\n[{html.escape(pmap[pid]['title'])}]\n{'DONE' if t['done'] else 'open'} · priority {t.get('priority', 0)}",
            'color': {'background': colors.get(pid, '#888'), 'border': '#222'},
            'shape': 'dot', 'size': 10 + (4 if t.get('priority', 0) >= 3 else 0),
            'opacity': 0.45 if t['done'] else 1.0,
            'font': {'color': '#bbb', 'size': 9}})
        meta[tid] = {'t': short(t['title'], 70), 'p': pmap[pid]['title'],
                     'prio': t.get('priority', 0) or 0, 'done': bool(t['done'])}
    gedges = []
    for a, b, k in edges:
        if a not in nodeids or b not in nodeids:
            continue
        if k == 'related':
            gedges.append({'from': a, 'to': b, 'dashes': True, 'color': {'color': '#7a7a7a', 'opacity': 0.5}, 'width': 1})
        else:
            gedges.append({'from': a, 'to': b, 'arrows': 'to', 'color': {'color': '#e0533d', 'opacity': 0.8}, 'width': 1.4})

    children = {}
    for p in projs:
        children.setdefault(p.get('parent_project_id') or 0, []).append(p['id'])

    def depmarks(t):
        rel = t.get('related_tasks') or {}
        out = []
        if rel.get('blocking'): out.append(f"blocks {len(rel['blocking'])}")
        if rel.get('blocked'): out.append(f"blocked by {len(rel['blocked'])}")
        if rel.get('related'): out.append(f"related {len(rel['related'])}")
        return ' · '.join(out)

    tasks_by_proj = {}
    for t in tasks:
        tasks_by_proj.setdefault(t['project_id'], []).append(t)

    def render_proj(pid, depth):
        p = pmap[pid]
        ts = sorted(tasks_by_proj.get(pid, []), key=lambda x: (x['done'], -(x.get('priority') or 0), x['id']))
        op = sum(1 for t in ts if not t['done']); dn = len(ts) - op
        c = colors.get(pid, '#888')
        rows = [f'<details class="proj" style="--pc:{c};margin-left:{depth*14}px" {"open" if depth<1 else ""}>']
        rows.append(f'<summary><span class="dot" style="background:{c}"></span><b>{html.escape(p["title"])}</b> <span class="pid">#{pid}</span> <span class="cnt">{op} open · {dn} done</span></summary>')
        for t in ts:
            cls = 'done' if t['done'] else ''
            pr = t.get('priority') or 0
            prb = f'<span class="pr pr{pr}">P{pr}</span>' if pr else ''
            labs = ' '.join(f'<span class="lab">{html.escape(l["title"])}</span>' for l in (t.get('labels') or []))
            dm = depmarks(t)
            dmh = f'<span class="dep">{dm}</span>' if dm else ''
            rows.append(f'<div class="task {cls}"><span class="st">{"✓" if t["done"] else "○"}</span> <span class="tid">#{t["id"]}</span> {prb} {html.escape(short(t["title"],90))} {labs} {dmh}</div>')
        for cid in sorted(children.get(pid, [])):
            rows.append(render_proj(cid, depth + 1))
        rows.append('</details>')
        return '\n'.join(rows)

    tree = ''.join(render_proj(pid, 0) for pid in sorted(children.get(0, [])))
    legend = ' '.join(f'<span class="lg"><span class="dot" style="background:{colors[pid]}"></span>{html.escape(pmap[pid]["title"])} <small>#{pid}</small></span>' for pid in pos_ids)
    tot = len(tasks); done = sum(1 for t in tasks if t['done'])
    today = datetime.date.today().isoformat()

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vikunja Map</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/dist/vis-network.min.js"></script>
<style>
:root{{--bg:#0f1115;--fg:#e6e6e6;--mut:#9aa0a8;--card:#171a21;--bd:#262b34}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif}}
header{{padding:16px 20px;border-bottom:1px solid var(--bd)}}
h1{{margin:0 0 4px;font-size:19px}}
.stats{{color:var(--mut);font-size:13px}} .stats b{{color:var(--fg)}}
.wrap{{padding:16px 20px;max-width:1400px;margin:0 auto}}
#net{{height:620px;background:#0b0d11;border:1px solid var(--bd);border-radius:10px}}
.controls{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:12px 0}}
.controls label{{font-size:13px;color:var(--mut);display:flex;gap:5px;align-items:center}}
select,button{{background:var(--card);color:var(--fg);border:1px solid var(--bd);border-radius:7px;padding:6px 10px;font-size:13px}}
.legend{{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0;font-size:12px;color:var(--mut)}}
.lg{{display:inline-flex;gap:4px;align-items:center}}
.dot{{width:10px;height:10px;border-radius:50%;display:inline-block;flex:0 0 auto}}
.key{{font-size:12px;color:var(--mut);margin:6px 0 2px}} .key b{{color:#e0533d}} .key i{{color:#7a7a7a;font-style:normal}}
h2{{font-size:16px;margin:26px 0 8px;border-top:1px solid var(--bd);padding-top:18px}}
details.proj{{border-left:3px solid var(--pc);padding:4px 0 4px 10px;margin:4px 0}}
summary{{cursor:pointer;list-style:none}} summary::-webkit-details-marker{{display:none}}
.pid{{color:var(--mut);font-size:12px}} .cnt{{color:var(--mut);font-size:12px;margin-left:6px}}
.task{{padding:2px 0 2px 22px;font-size:13px;color:var(--fg)}}
.task.done{{color:#5f6670;text-decoration:line-through}}
.st{{color:#4fae6b}} .task.done .st{{color:#5f6670}}
.tid{{color:var(--mut);font-size:12px}}
.pr{{font-size:10px;padding:0 4px;border-radius:4px;border:1px solid var(--bd)}}
.pr3,.pr4,.pr5{{color:#f2c14e;border-color:#6a5a2a}} .pr1,.pr2{{color:var(--mut)}}
.lab{{font-size:10px;background:#20252e;border:1px solid var(--bd);border-radius:10px;padding:0 6px;color:#b7c3d0}}
.dep{{font-size:10px;color:#e0893d}}
.netwrap{{position:relative}}
#panel{{position:absolute;top:10px;right:10px;width:300px;max-height:88%;overflow:auto;background:rgba(16,19,24,.96);border:1px solid var(--bd);border-radius:8px;padding:10px 12px;font-size:12px;box-shadow:0 6px 20px rgba(0,0,0,.4)}}
#panel.hidden{{display:none}}
.phdr{{font-weight:600;font-size:13px;margin-bottom:2px}}
.psub{{color:var(--mut);margin-bottom:8px}}
.prow{{margin:3px 0}} .prow b{{color:#f2c14e}}
.plist{{margin-top:8px;border-top:1px solid var(--bd);padding-top:6px;line-height:1.5}}
.pp{{color:var(--mut);font-size:10px}}
.pnote{{margin-top:8px;color:var(--mut);font-size:10px;font-style:italic}}
@media(prefers-color-scheme:light){{:root{{--bg:#f7f8fa;--fg:#1a1d22;--mut:#5a626c;--card:#fff;--bd:#dce0e6}}#net{{background:#fff}}}}
</style></head><body>
<header><h1>Vikunja Map — projects, tasks &amp; dependencies</h1>
<div class="stats">Generated {today} · <b>{len(pos_ids)}</b> projects · <b>{tot}</b> tasks (<b>{tot-done}</b> open, {done} done) · <b>{len(edges)}</b> dependencies · {len(gnodes)} tasks in the graph</div></header>
<div class="wrap">
<div class="controls">
<label>Project: <select id="pf"><option value="">— all —</option>{''.join(f'<option value="{pid}">{html.escape(pmap[pid]["title"])}</option>' for pid in pos_ids)}</select></label>
<label><input type="checkbox" id="rel" checked> show "related"</label>
<label><input type="checkbox" id="phys" checked> physics</label>
<button id="fit">Fit</button>
<button id="crit">Critical path</button>
<button id="reset">Clear selection</button>
</div>
<div class="key">Red <b>arrows</b> = "blocks" (A → B: A blocks B) · <i>grey dashed</i> = "related" · faded nodes = done · bigger nodes = priority ≥3</div>
<div class="netwrap"><div id="net"></div><div id="panel" class="hidden">Click a task to see what it unblocks, or use "Critical path".</div></div>
<div class="legend">{legend}</div>
<h2>Full tree — all projects and tasks</h2>
{tree}
</div>
<script>
const NODES={json.dumps(gnodes)};
const EDGES={json.dumps(gedges)};
const META={json.dumps(meta)};
const nodes=new vis.DataSet(NODES);
const alledges=EDGES;
let edges=new vis.DataSet(alledges);
const container=document.getElementById('net');
const network=new vis.Network(container,{{nodes:nodes,edges:edges}},{{
 physics:{{enabled:true,barnesHut:{{gravitationalConstant:-8000,springLength:120,springConstant:0.04,damping:0.4}},stabilization:{{iterations:250}}}},
 interaction:{{hover:true,tooltipDelay:120}},
 nodes:{{borderWidth:1}},edges:{{smooth:{{type:'continuous'}}}}
}});
const fwd={{}},rev={{}};
alledges.forEach(e=>{{ if(!e.dashes){{ (fwd[e.from]=fwd[e.from]||[]).push(e.to); (rev[e.to]=rev[e.to]||[]).push(e.from); }} }});
const eff=id=>{{ const m=META[id]; return (m&&m.prio)?m.prio:2; }};
const isDone=id=>!!(META[id]&&META[id].done);
// direct OPEN successors; done tasks are traversed (bridged) but not counted
function succOpen(n){{ const out=new Set(),seen=new Set(),st=(fwd[n]||[]).slice();
 while(st.length){{ const m=st.pop(); if(seen.has(m))continue; seen.add(m);
  if(isDone(m)){{ (fwd[m]||[]).forEach(x=>st.push(x)); }} else out.add(m); }} return [...out]; }}
function downOpen(start){{ const seen=new Set(),st=succOpen(start);
 while(st.length){{ const n=st.pop(); if(seen.has(n))continue; seen.add(n); succOpen(n).forEach(m=>{{ if(!seen.has(m))st.push(m); }}); }} return seen; }}
// reachable over ALL nodes (including done bridges), used only to highlight the corridor
function reachAll(start){{ const seen=new Set(),st=(fwd[start]||[]).slice();
 while(st.length){{ const n=st.pop(); if(seen.has(n))continue; seen.add(n); (fwd[n]||[]).forEach(m=>{{ if(!seen.has(m))st.push(m); }}); }} return seen; }}
const memo={{}};
function longest(n){{ if(memo[n])return memo[n]; const self=isDone(n)?0:eff(n); memo[n]={{w:self,path:isDone(n)?[]:[n]}};
 let best={{w:0,path:[]}}; succOpen(n).forEach(m=>{{ const r=longest(m); if(r.w>best.w)best=r; }});
 const res={{w:self+best.w,path:(isDone(n)?[]:[n]).concat(best.path)}}; memo[n]=res; return res; }}
// expand an open-only path by re-inserting bridged done nodes, for a continuous line
function expand(path){{ const route=new Set(path);
 for(let i=0;i<path.length-1;i++){{ const target=path[i+1],seen=new Set([path[i]]),q=[[path[i]]]; let found=null;
  while(q.length&&!found){{ const cur=q.shift(),last=cur[cur.length-1],succ=fwd[last]||[];
   for(let j=0;j<succ.length;j++){{ const m=succ[j];
    if(m===target){{ found=cur.concat(m); break; }}
    if(isDone(m)&&!seen.has(m)){{ seen.add(m); q.push(cur.concat(m)); }} }} }}
  if(found) found.forEach(x=>route.add(x)); }} return route; }}
function esc(s){{ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;'); }}
function fmt(id){{ const m=META[id]||{{}}; return '#'+id+' '+esc(m.t); }}
function relOn(){{ return document.getElementById('rel').checked; }}
const panel=document.getElementById('panel');
function applyFilters(){{
 const pf=document.getElementById('pf').value;
 const showrel=relOn();
 edges.clear(); edges.add(alledges.filter(e=> showrel? true : !e.dashes));
 const ptxt = pf? document.querySelector('#pf option[value="'+pf+'"]').textContent : null;
 nodes.update(NODES.map(n=>{{
   const vis2 = !ptxt || n.title.includes('['+ptxt+']');
   return {{id:n.id,opacity: vis2? n.opacity : 0.08, font:{{color: vis2?'#bbb':'#2a2a2a',size:9}}}};
 }}));
}}
function highlightSet(ids){{
 const set=new Set(ids);
 nodes.update(NODES.map(n=>({{id:n.id,opacity:set.has(n.id)?1.0:0.08,font:{{color:set.has(n.id)?'#fff':'#2a2a2a',size:9}}}})));
 edges.clear();
 edges.add(alledges.map(e=>{{ const on=set.has(e.from)&&set.has(e.to)&&!e.dashes; return Object.assign({{}},e,{{color:{{color:on?'#ffb454':(e.dashes?'#7a7a7a':'#e0533d'),opacity:on?1:0.12}},width:on?2.4:1}}); }}).filter(e=> relOn()?true:!e.dashes));
}}
function showTask(sel){{
 const direct=succOpen(sel); const down=downOpen(sel); const arr=[...down];
 let w=0; arr.forEach(id=>w+=eff(id)); const lp=longest(sel); const m=META[sel]||{{}};
 let h='<div class="phdr">'+fmt(sel)+'</div>';
 h+='<div class="psub">['+esc(m.p)+'] · '+(m.done?'DONE':'open')+' · priority '+(m.prio||0)+'</div>';
 h+='<div class="prow">Directly unblocks: <b>'+direct.length+'</b></div>';
 h+='<div class="prow">Downstream: <b>'+arr.length+'</b> tasks · proxy weight ~<b>'+w+'</b></div>';
 h+='<div class="prow">Longest chain from here: <b>'+lp.path.length+'</b> tasks · weight ~<b>'+lp.w+'</b></div>';
 if(arr.length){{ h+='<div class="plist">'+arr.slice(0,25).map(id=>'<div>• '+fmt(id)+' <span class="pp">P'+((META[id]||{{}}).prio||0)+'</span></div>').join('')+(arr.length>25?'<div>…+'+(arr.length-25)+' more</div>':'')+'</div>'; }}
 h+='<div class="pnote">done/cancelled tasks excluded · proxy weight = sum of priorities (replace with real sizes)</div>';
 panel.innerHTML=h; panel.classList.remove('hidden');
 const hl=new Set([sel]); reachAll(sel).forEach(x=>hl.add(x));
 highlightSet([...hl]);
}}
network.on('click',p=>{{ if(p.nodes.length){{ showTask(p.nodes[0]); }} else {{ panel.classList.add('hidden'); applyFilters(); }} }});
document.getElementById('pf').onchange=applyFilters;
document.getElementById('rel').onchange=applyFilters;
document.getElementById('phys').onchange=e=>network.setOptions({{physics:{{enabled:e.target.checked}}}});
document.getElementById('fit').onclick=()=>network.fit({{animation:true}});
document.getElementById('reset').onclick=()=>{{ panel.classList.add('hidden'); applyFilters(); }};
document.getElementById('crit').onclick=()=>{{
 let best={{w:0,path:[]}}; Object.keys(META).forEach(id=>{{ if(isDone(+id))return; const r=longest(+id); if(r.w>best.w)best=r; }});
 if(!best.path.length)return;
 let h='<div class="phdr">Critical path</div><div class="psub">longest blocking chain among <b>open</b> tasks · '+best.path.length+' tasks · weight ~'+best.w+'</div><div class="plist">'+best.path.map((id,i)=>'<div>'+(i+1)+'. '+fmt(id)+' <span class="pp">P'+((META[id]||{{}}).prio||0)+'</span></div>').join('')+'</div><div class="pnote">done/cancelled tasks excluded · proxy weight = sum of priorities</div>';
 panel.innerHTML=h; panel.classList.remove('hidden');
 const route=expand(best.path);
 nodes.update(NODES.map(n=>({{id:n.id,opacity:route.has(n.id)?1:0.07,font:{{color:route.has(n.id)?'#fff':'#2a2a2a',size:9}}}})));
 edges.clear();
 edges.add(alledges.map(e=>{{ const on=route.has(e.from)&&route.has(e.to)&&!e.dashes; return Object.assign({{}},e,{{color:{{color:on?'#59d98e':(e.dashes?'#7a7a7a':'#e0533d'),opacity:on?1:0.08}},width:on?3:1}}); }}).filter(e=> relOn()?true:!e.dashes));
}};
network.on('stabilizationIterationsDone',()=>network.setOptions({{physics:{{enabled:document.getElementById('phys').checked}}}}));
</script>
</body></html>"""


def generate():
    """Fetch live data and return the rendered HTML page."""
    return build(*fetch())
