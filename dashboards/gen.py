#!/usr/bin/env python3
"""Generate the poco dashboard JSON into the grafana-dashboards checkout. Never touch the JSON by hand, never the GUI.

    ./dev                         save-to-preview loop (regenerate + copy to the phone)
    python3 gen.py                one-shot; then commit here (source) and in grafana-dashboards (json), push both

Output: $DASHBOARDS/poco/poco.json, DASHBOARDS defaults to the sibling checkout ../../grafana-dashboards.

The service graph comes from topology.py (diagrams DSL, same file renders the README png).
"""
import json

DS = {"type": "prometheus", "uid": "prom"}

BOX_W, BOX_H, GRID_W, GRID_H, PAD = 150, 56, 185, 74, 16    # graphviz order, snapped to a GRID_W x GRID_H px grid


def topology():
    """Run topology.py as dot, graphviz lays it out, positions snap to a grid. Returns nodes {key: attrs + left,top px}, edges."""
    import os, subprocess, sys
    here = os.path.dirname(os.path.abspath(__file__))
    subprocess.run([sys.executable, "topology.py"], cwd=here, env={**os.environ, "OUT": "dot"}, check=True)
    g = json.loads(subprocess.run(["dot", "-Tjson", "topology.dot"], cwd=here, check=True,
                                  capture_output=True, text=True).stdout)
    objs = g["objects"]
    nodes = {o["key"]: o for o in objs if "key" in o and "pos" in o}
    def ranks(vals, tol=24):    # graphviz coordinate -> index of its column/row, positions closer than tol pt share one
        levels = []
        for v in sorted(set(vals)):
            if not levels or v - levels[-1] > tol:
                levels.append(v)
        return lambda v: max(i for i, l in enumerate(levels) if v >= l - tol)
    col = ranks([float(o["pos"].split(",")[0]) for o in nodes.values()])
    row = ranks([-float(o["pos"].split(",")[1]) for o in nodes.values()])    # graphviz y points up
    for o in nodes.values():
        x, y = (float(v) for v in o["pos"].split(","))
        c, r = (int(v) for v in o["at"].split(",")) if "at" in o else (col(x), row(-y))
        o["left"], o["top"] = PAD + c * GRID_W, PAD + r * GRID_H
    edges = [(objs[e["tail"]].get("key"), objs[e["head"]].get("key")) for e in g.get("edges", [])]
    return nodes, [(a, b) for a, b in edges if a in nodes and b in nodes]


def canvas(x, y, w):
    """Service graph from topology.py. Boxes coloured by `up`, `rpm` printed inside, arrows from the edges."""
    nodes, edges = topology()
    elements, targets = [], []
    for i, (key, n) in enumerate(sorted(nodes.items(), key=lambda kv: (kv[1]["top"], kv[1]["left"]))):
        if "up" in n:
            targets.append({"refId": "u%d" % i, "expr": n["up"], "legendFormat": key, "instant": True, "range": False})
        if "rpm" in n:
            targets.append({"refId": "r%d" % i, "expr": n["rpm"], "legendFormat": key + " rpm", "instant": True, "range": False})
        bg = {"field": key, "fixed": "#D9D9D9"} if "up" in n else {"fixed": "#5a5a5a"}
        left, top = round(n["left"]), round(n["top"])
        elements.append({
            "name": key, "type": "rectangle",
            "config": {"align": "center", "valign": "top", "size": 12, "color": {"fixed": "#ffffff"},
                       "text": {"mode": "fixed", "fixed": n.get("label", key)}, "backgroundColor": bg},
            "background": {"color": bg},
            "border": {"color": {"fixed": "transparent"}, "width": 1},
            "placement": {"top": top, "left": left, "width": BOX_W, "height": BOX_H, "rotation": 0},
            "constraint": {"vertical": "top", "horizontal": "left"},
            "links": [],
            "connections": [{"source": {"x": 1, "y": 0}, "target": {"x": -1, "y": 0}, "targetName": b,
                             "color": {"fixed": "#9e9e9e"}, "size": {"fixed": 2}, "path": "straight", "vertices": []}
                            for a, b in edges if a == key],
        })
        if "rpm" in n:
            elements.append({
                "name": key + " rpm", "type": "metric-value",
                "config": {"align": "center", "valign": "middle", "size": 16, "color": {"fixed": "#ffffff"},
                           "text": {"mode": "field", "field": key + " rpm"}},
                "background": {"color": {"fixed": "transparent"}},
                "border": {"color": {"fixed": "transparent"}, "width": 0},
                "placement": {"top": top + 22, "left": left, "width": BOX_W, "height": BOX_H - 22, "rotation": 0},
                "constraint": {"vertical": "top", "horizontal": "left"},
                "links": [], "connections": [],
            })
    bottom = max(round(n["top"]) for n in nodes.values()) + BOX_H + PAD
    h = -(-bottom // 30) + 1    # grid row ~30 px, + title bar
    return {
        "id": 0, "type": "canvas", "title": "service graph (req/min, colour = up)",
        "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": DS, "targets": targets,
        "options": {"inlineEditing": False, "showAdvancedTypes": True, "panZoom": False, "infinitePan": False,
                    "root": {"name": "graph", "type": "frame", "elements": elements,
                             "background": {"color": {"fixed": "transparent"}},
                             "border": {"color": {"fixed": "transparent"}},
                             "constraint": {"vertical": "top", "horizontal": "left"},
                             "placement": {"top": 0, "left": 0, "width": 100, "height": 100}}},
        "fieldConfig": {"defaults": {"decimals": 0, "unit": "reqpm",
                                     "thresholds": {"mode": "absolute",
                                                    "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}},
                        "overrides": []},
    }, h


def panel(typ, title, x, y, w, h, targets, unit=None, mn=None, mx=None, dec=None,
          steps=None, mappings=None, overrides=None, instant=False):
    d = {}
    if unit: d["unit"] = unit
    if mn is not None: d["min"] = mn
    if mx is not None: d["max"] = mx
    if dec is not None: d["decimals"] = dec
    if steps: d["thresholds"] = {"mode": "absolute", "steps": [{"color": c, "value": v} for c, v in steps]}
    if mappings: d["mappings"] = mappings
    p = {"id": 0, "type": typ, "title": title, "gridPos": {"x": x, "y": y, "w": w, "h": h}, "datasource": DS,
         "targets": [{"refId": chr(65 + i), "expr": e, "legendFormat": l, "instant": instant, "range": not instant}
                     for i, (e, l) in enumerate(targets)],
         "fieldConfig": {"defaults": d, "overrides": overrides or []}, "options": {}}
    if typ == "stat":
        p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none",
                        "textMode": "value_and_name", "justifyMode": "center", "text": {"titleSize": 18, "valueSize": 34}}
    return p


UPDOWN = [{"type": "value", "options": {"0": {"text": "DOWN", "color": "red"}, "1": {"text": "UP", "color": "green"}}}]
FREE_PCT_OVERRIDE = [{"matcher": {"id": "byName", "options": "free %"}, "properties": [
    {"id": "unit", "value": "percentunit"}, {"id": "decimals", "value": 0}, {"id": "min", "value": 0}, {"id": "max", "value": 1},
    {"id": "thresholds", "value": {"mode": "absolute", "steps": [
        {"color": "red", "value": None}, {"color": "yellow", "value": 0.1}, {"color": "green", "value": 0.25}]}}]}]

P, Y = [], [0]


def row(title):
    P.append({"id": 0, "type": "row", "title": title, "collapsed": False,
              "gridPos": {"x": 0, "y": Y[0], "w": 24, "h": 1}, "panels": []})
    Y[0] += 1


def add(p, h):
    P.append(p); return h


def endrow(h):
    Y[0] += h


row("overview")
add(panel("stat", "probes", 0, Y[0], 24, 6, [("probe_success", "{{name}}")], instant=True,
          steps=[("red", None), ("green", 1)], mappings=UPDOWN), 6)
endrow(6)
add(panel("stat", "cert days left", 0, Y[0], 12, 5,
          [("min((probe_ssl_earliest_cert_expiry - time()) / 86400)", "wildcard")], instant=True, dec=0,
          steps=[("red", None), ("yellow", 3), ("green", 30)]), 5)
add(panel("stat", "firing", 12, Y[0], 12, 5,
          [('count(ALERTS{alertstate="firing", alertname!="Watchdog"}) or vector(0)', "alerts")], instant=True, dec=0,
          steps=[("green", None), ("red", 1)]), 5)
endrow(5)

row("service graph")
cv, cv_h = canvas(0, Y[0], 24)
P.append(cv)
endrow(cv_h)

row("web traffic (haproxy :8443)")
add(panel("timeseries", "requests / min per backend", 0, Y[0], 12, 7,
          [("rate(haproxy_backend_sessions_total[5m]) * 60", "{{backend}}")], unit="reqpm"), 7)
add(panel("timeseries", "responses / min by status", 12, Y[0], 12, 7,
          [("sum by (code) (rate(haproxy_backend_http_responses_total[5m])) * 60", "{{code}}")], unit="reqpm"), 7)
endrow(7)
add(panel("stat", "requests today", 0, Y[0], 8, 5,
          [("sum by (backend) (increase(haproxy_backend_sessions_total[1d]))", "{{backend}}")], instant=True, dec=0,
          steps=[("blue", None)]), 5)
add(panel("stat", "requests this week", 8, Y[0], 8, 5,
          [("sum by (backend) (increase(haproxy_backend_sessions_total[7d]))", "{{backend}}")], instant=True, dec=0,
          steps=[("blue", None)]), 5)
add(panel("timeseries", "response bytes / min", 16, Y[0], 8, 5,
          [("sum by (backend) (rate(haproxy_backend_bytes_out_total[5m])) * 60", "{{backend}}")], unit="bytes"), 5)
endrow(5)

for app in ("shoko", "mealprep"):
    row(app)
    add(panel("timeseries", "anubis-%s: proxied / challenged per min" % app, 0, Y[0], 12, 5,
              [('sum(rate(anubis_proxied_requests_total{app="%s"}[5m])) * 60' % app, "proxied"),
               ('sum(rate(anubis_challenges_issued{app="%s"}[5m])) * 60' % app, "challenged")], unit="reqpm"), 5)
    add(panel("timeseries", "%s backend: requests / min" % app, 12, Y[0], 12, 5,
              [('rate(haproxy_backend_sessions_total{backend="%s"}[5m]) * 60' % app, app),
               ('rate(haproxy_backend_http_responses_total{backend="%s",code="5xx"}[5m]) * 60' % app, "5xx")], unit="reqpm"), 5)
    endrow(5)

row("host: cpu & memory")
add(panel("timeseries", "cpu busy per core", 0, Y[0], 8, 7, [("termux_cpu_busy_ratio", "cpu{{cpu}}")],
          unit="percentunit", mn=0, mx=1), 7)
add(panel("timeseries", "load", 8, Y[0], 8, 7,
          [("termux_load1", "1m"), ("termux_load5", "5m"), ("termux_load15", "15m")]), 7)
add(panel("timeseries", "memory", 16, Y[0], 8, 7,
          [("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "used"),
           ("node_memory_SwapTotal_bytes - node_memory_SwapFree_bytes", "swap used")], unit="bytes"), 7)
endrow(7)

row("host: power & thermal")
add(panel("timeseries", "battery", 0, Y[0], 8, 6, [("termux_battery_percent", "%")], unit="percent", mn=0, mx=100), 6)
add(panel("timeseries", "battery current (neg = charging)", 8, Y[0], 8, 6,
          [("termux_battery_current_amps", "A")], unit="amp"), 6)
add(panel("timeseries", "temperature", 16, Y[0], 8, 6,
          [("max(termux_cpu_temperature_celsius)", "cpu max zone"),
           ("termux_battery_temperature_celsius", "battery")], unit="celsius"), 6)
endrow(6)

row("storage")
for mp, label in (("/data", "/data (termux, shoko db, models)"),
                  ("/storage/EABF-DEDA", "/storage/EABF-DEDA (usb ssd, anime)")):
    free = 'max by (mountpoint) (node_filesystem_avail_bytes{mountpoint="%s"})' % mp
    pct = ('max by (mountpoint) (node_filesystem_avail_bytes{mountpoint="%s"} '
           '/ node_filesystem_size_bytes{mountpoint="%s"})' % (mp, mp))
    add(panel("timeseries", label, 0, Y[0], 16, 6, [(free, "free")], unit="bytes", mn=0), 6)
    add(panel("stat", "free", 16, Y[0], 8, 6, [(free, "free"), (pct, "free %")], instant=True, unit="bytes", dec=0,
              steps=[("green", None)], overrides=FREE_PCT_OVERRIDE), 6)
    endrow(6)
add(panel("timeseries", "usb ssd fuse latency (listdir, 1 MiB read)", 0, Y[0], 24, 6,
          [("termux_fuse_listdir_seconds", "listdir"), ("termux_fuse_read1m_seconds", "read 1 MiB")], unit="s", mn=0), 6)
endrow(6)

for i, p in enumerate(P, 1):
    p["id"] = i
import os
out = os.path.join(os.environ.get("DASHBOARDS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "grafana-dashboards")), "poco", "poco.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
json.dump({"uid": "poco", "title": "poco", "timezone": "browser", "refresh": "1m",
           "time": {"from": "now-24h", "to": "now"}, "schemaVersion": 39,
           "panels": P, "templating": {"list": []}},
          open(out, "w"), indent=1)
print(os.path.relpath(out), len(P), "panels,", len([p for p in P if p["type"] == "row"]), "rows")
