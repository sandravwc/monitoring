# monitoring

Prometheus, Alertmanager, blackbox_exporter, node_exporter and Grafana on
the Poco under Termux, rootless. Upstream `linux-arm64` static binaries,
runit services, alerts to ntfy (`?template=alertmanager`, no bridge), a
dead-man's check from the workstation.

```txt
 poco f5 pro                                                        workstation
┌──────────────────────────────────────────────────────────┐       ┌──────────────────────┐
│ prometheus :9090 ─► alertmanager :9093 ─► tinyproxy :8118 ─► ntfy │ ◄─ssh─┤ timer */30 deadman.sh│
│   │  scrape                                              │       │  ntfy if unreachable │
│   ├─► node_exporter :9100  meminfo, /data, cpufreq       │       └──────────────────────┘
│   │     textfile.sh: battery, load, cpu busy, thermal    │
│   ├─► anubis metrics :9917 :9091, haproxy_exporter :9101 │
│   └─► blackbox :9115 ─ http/tcp ─► haproxy :8443 ─► anubis ─► shoko / mealprep; nfs, sshd
│ grafana :3000 ─► prometheus                              │
│ haproxy :8443: prom. alerts. (basic auth)  grafana. (own login)
└──────────────────────────────────────────────────────────┘
```

Nagios → here: NRPE = `node_exporter`; check_http/tcp/ssl =
`blackbox_exporter`; service checks = rules in
`alerts.yml`; notification commands = Alertmanager receivers; `textfile.sh` =
custom checks via the textfile collector.

## Layout

```txt
deploy/fetch.sh              downloads an upstream linux-arm64 build into ~/monitoring/bin
deploy/prometheus.yml        scrape targets: node on both phones, blackbox http/tcp
deploy/alerts.yml            rules: down, probe failed, cert < 14d, disk, thermal, swap, load, cpu, battery
deploy/alertmanager.yml      route everything to ntfy, drop Watchdog; topic url read from ~/monitoring/ntfy.url
deploy/blackbox.yml          http_2xx (follows redirects), tcp_connect
deploy/textfile.sh           cron */1: battery, load (sysinfo), cpu idle (cpuidle sysfs), thermal, fuse latency on the ssd -> ~/monitoring/textfile/termux.prom
deploy/sv-haproxy-exporter.run  haproxy_exporter on the stats socket (termux haproxy has no PROMEX)
deploy/tinyproxy.conf        local forward proxy: DNS for the Go binaries (they can't resolve on Android)
deploy/haproxy.cfg           backends prom, alerts, grafana; symlinked into ~/haproxy.d/
deploy/grafana.ini           grafana on 127.0.0.1:3000, data in ~/monitoring/grafana, provisioning from the repo
deploy/grafana/              provisioned prometheus datasource; dashboards come from `sandravwc/grafana-dashboards` cloned to ~/monitoring/dashboards
deploy/sv-*.run              runit services
deploy/deadman.sh            workstation cron: ntfy when the Poco's Prometheus is unreachable
```

On the Poco, outside the repo: `~/monitoring/{bin,data,alertmanager,textfile}`,
`~/monitoring/ntfy.url` (secret, `https://ntfy.sh/<topic>?template=alertmanager`).

## Install

### Poco: node_exporter + textfile.sh

```sh
pkg install termux-services termux-api python    # termux-api needs the Termux:API app too
git clone https://github.com/sandravwc/monitoring ~/monitoring/repo
~/monitoring/repo/deploy/fetch.sh node_exporter 1.8.2     # pinned, newer ones die with SIGSYS on Android
mkdir -p ~/monitoring/textfile $PREFIX/var/service/node-exporter
cp ~/monitoring/repo/deploy/sv-node-exporter.run $PREFIX/var/service/node-exporter/run
export SVDIR=$PREFIX/var/service; sv up node-exporter
(crontab -l 2>/dev/null; echo '* * * * * $HOME/monitoring/repo/deploy/textfile.sh') | crontab -
curl -s localhost:9100/metrics | grep -E '^termux_' | head
```

Collectors are an allowlist, not the defaults. Android denies apps
`/proc/stat`, `/proc/loadavg`, `/proc/vmstat`, `/proc/uptime`, `/proc/net`,
netlink and parts of `/sys`. What works in node_exporter: meminfo, filesystem
(`/data`), cpufreq, uname, time, textfile. `textfile.sh` fills the rest by
side doors: load from the `sysinfo()` syscall (what bionic's `getloadavg`
does), per-core idle time from `cpuidle` sysfs (`1 - rate()` = busy, same
math as `/proc/stat`), thermal from the cpu zones (the built-in collector
fails on the first denied zone), battery from `termux-battery-status`. No
network metrics, ever.
`/data` is the filesystem that matters; the exclude list hides Android's 30
pseudo mounts.

### Poco: Prometheus, Alertmanager, blackbox

```sh
pkg install tinyproxy
for c in prometheus alertmanager blackbox_exporter haproxy_exporter; do ~/monitoring/repo/deploy/fetch.sh $c; done
# haproxy: `stats socket ~/haproxy.sock mode 600 level operator` in the global section (see shoko-termux/deploy/haproxy-base.cfg)
echo 'https://ntfy.sh/<topic>?template=alertmanager' > ~/monitoring/ntfy.url; chmod 600 ~/monitoring/ntfy.url
for s in tinyproxy prometheus alertmanager blackbox haproxy-exporter; do mkdir -p $PREFIX/var/service/$s; cp ~/monitoring/repo/deploy/sv-$s.run $PREFIX/var/service/$s/run; done
sv up tinyproxy prometheus alertmanager blackbox haproxy-exporter
~/monitoring/bin/prometheus --config.file ~/monitoring/repo/deploy/prometheus.yml --check-config   # promtool is in the tarball too
```

Subscribe to the topic in the ntfy app.

### Web UIs: prom., alerts., grafana.

Everything binds 127.0.0.1; haproxy (`~/haproxy.d`, see shoko-termux) puts
them on the wildcard cert. Prometheus and Alertmanager have no login and
every loopback client (Prometheus → Alertmanager, Grafana → Prometheus,
self-scrape) would need the password if they had one, so haproxy asks at the
edge instead. Termux's haproxy lacks `crypt(3)`: the userlist is plaintext,
so it lives outside the repo in `~/haproxy.d/05-auth.cfg`, 0600. Grafana logs
in itself.

```sh
pkg install grafana
echo 'GF_SECURITY_ADMIN_PASSWORD=<pw>' > ~/monitoring/grafana.env; chmod 600 ~/monitoring/grafana.env
printf 'userlist monitoring\n    user mrk insecure-password <pw>\n' > ~/haproxy.d/05-auth.cfg; chmod 600 ~/haproxy.d/05-auth.cfg
mkdir -p ~/monitoring/grafana $PREFIX/var/service/grafana
git clone https://github.com/sandravwc/grafana-dashboards ~/monitoring/dashboards
cp ~/monitoring/repo/deploy/sv-grafana.run $PREFIX/var/service/grafana/run; sv up grafana
ln -s ~/monitoring/repo/deploy/haproxy.cfg ~/haproxy.d/30-monitoring.cfg; haproxy -c -f ~/haproxy.d && sv restart haproxy
# dns: prom, alerts, grafana as CNAME -> poco
```

https://prom.poco.xn--bdk.dog:8443 (`/alerts`, `/targets`, `/graph`),
https://alerts.poco.xn--bdk.dog:8443 (silences), https://grafana.poco.xn--bdk.dog:8443
(dashboard "poco": cpu, load, memory, temperature, battery, disk, probes,
cert, anubis). Alert pushes link back to `prom.` via `--web.external-url`.
Tunnel still works: `ssh -L 9090:127.0.0.1:9090 poco`.

Test an alert without breaking anything:

```sh
~/monitoring/bin/amtool --alertmanager.url=http://127.0.0.1:9093 alert add test severity=warning host=nothing --annotation=summary="ntfy test"
```

## Operate

- Change a rule/target: edit in the workstation clone, push, `git pull` on the Nothing, `sv restart prometheus` (or `kill -HUP` for a config reload)
- Logs: `$PREFIX/var/log/sv/<svc>/current`
- Update a binary: `fetch.sh <name>`, `sv restart <svc>`; grafana via `pkg upgrade`
- Dashboards: `sandravwc/grafana-dashboards`, provisioned read-only; edit JSON there, push, `git pull` in `~/monitoring/dashboards`
- Dead monitor: `deadman.sh` from the workstation, systemd user timer (`deploy/monitoring-deadman.{service,timer}` → `~/.config/systemd/user/`, `systemctl --user enable --now monitoring-deadman.timer`), topic url in `~/.config/monitoring-ntfy.url`. Only fires while the workstation is awake; the `Watchdog` alert (always firing, blackholed) shows in `/alerts` that rules evaluate
- Data: 90 d retention, ~1 GB/yr at this size

## Gotchas

- node_exporter ≥ 1.9 calls `open_tree()` (filepath-securejoin), Android seccomp answers SIGSYS, process dies on first scrape. 1.8.2 pinned
- `/sys/class/thermal`: cpu zones readable, others not; `hwmon`, `pressure`, `/sys/fs/fuse/connections` denied. FUSE queue depth is not readable, so `textfile.sh` times a listdir and a 1 MiB read on the SSD instead
- Go's pure resolver reads `/etc/resolv.conf`, Android has none, and port 53 can't be bound for a local forwarder: no Go binary here can resolve a hostname. Fix: `tinyproxy` (bionic, resolves fine) on 127.0.0.1:8118, `proxy_url` in Alertmanager's webhook and blackbox's `http_public` module. Scrape targets stay IPs
- Go finds no CA bundle either (`/etc/ssl`): `SSL_CERT_FILE=$PREFIX/etc/tls/cert.pem` in every run script
- Alertmanager: `--cluster.listen-address=""`, gossip setup needs netlink
- `termux-battery-status` current sign: negative = charging on Xiaomi kernels; `BatteryDraining` alert relies on it
- HyperOS kills Termux when idle: `termux-wake-lock` + battery optimization off for Termux, or the monitor vanishes with everything else (that is what `deadman.sh` is for)
