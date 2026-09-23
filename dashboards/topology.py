#!/usr/bin/env python3
"""Service topology, diagrams DSL. One source, two outputs:

    python3 topology.py        -> topology.png (README)
    python3 gen.py             -> runs this with OUT=dot, graphviz lays it out, canvas panel in poco.json

Node attributes (all optional, ignored by the PNG):
    key   stable id. Required on every node the canvas should draw (diagrams' own node ids are random)
    addr  where it listens. Documentation, shown nowhere yet
    up    PromQL returning one 0/1 series. Colours the box: 0 red, 1 green. No `up` = grey
    rpm   PromQL returning one series. Printed in the box as req/min
    at    "col,row" pins the box to a grid cell instead of graphviz' position
Clusters draw in the PNG only.
"""
import os
from diagrams import Diagram, Cluster
from diagrams.onprem.client import Users
from diagrams.onprem.network import Haproxy
from diagrams.onprem.monitoring import Grafana, Prometheus
from diagrams.generic.network import Firewall
from diagrams.generic.compute import Rack
from diagrams.generic.storage import Storage

sessions = 'rate(haproxy_backend_sessions_total{backend="%s"}[5m]) * 60'

with Diagram("poco", show=False, filename="topology", outformat=os.environ.get("OUT", "png"), direction="LR"):
    internet = Users("internet", key="internet")
    with Cluster("poco f5 pro"):
        haproxy = Haproxy("haproxy :8443", key="haproxy", addr="0.0.0.0:8443",
                          up="haproxy_up", rpm="sum(rate(haproxy_backend_sessions_total[5m])) * 60")
        with Cluster("shoko"):
            anubis_shoko = Firewall("anubis :8924", key="anubis-shoko", addr="127.0.0.1:8924",
                                    up='up{job="anubis", app="shoko"}',
                                    rpm='sum(rate(anubis_proxied_requests_total{app="shoko"}[5m])) * 60')
            shoko = Rack("shoko :8111", key="shoko", addr="127.0.0.1:8111",
                         up='probe_success{name="shoko api"}', rpm=sessions % "shoko")
        with Cluster("mealprep"):
            anubis_mealprep = Firewall("anubis :8923", key="anubis-mealprep", addr="127.0.0.1:8923",
                                       up='up{job="anubis", app="mealprep"}',
                                       rpm='sum(rate(anubis_proxied_requests_total{app="mealprep"}[5m])) * 60')
            mealprep = Rack("mealprep :8090", key="mealprep", addr="127.0.0.1:8090",
                            up='probe_success{name="mealprep app"}', rpm=sessions % "mealprep")
        with Cluster("monitoring"):
            grafana = Grafana("grafana :3000", key="grafana", addr="127.0.0.1:3000",
                              up='haproxy_backend_up{backend="grafana"}', rpm=sessions % "grafana")
            prom = Prometheus("prometheus :9090", key="prom", addr="127.0.0.1:9090",
                              up='up{job="prometheus"}', rpm=sessions % "prom")
            alerts = Rack("alertmanager :9093", key="alerts", addr="127.0.0.1:9093",
                          up='haproxy_backend_up{backend="alerts"}', rpm=sessions % "alerts")
        with Cluster("lan"):
            nfs = Storage("nfs :2049", key="nfs", addr="192.168.1.106:2049", up='probe_success{name="nfs"}')
            sshd = Rack("sshd :8022", key="sshd", addr="192.168.1.106:8022", up='probe_success{name="sshd"}')

    internet >> haproxy
    haproxy >> [anubis_shoko, anubis_mealprep, grafana, prom, alerts]
    anubis_shoko >> shoko
    anubis_mealprep >> mealprep
