# monitoring

Prometheus + Alertmanager for the phone fleet, running on a phone. Nagios
shape (checks, thresholds, pushes) with Go static binaries that run rootless
in Termux. Monitor host is the Nothing Phone 2: separate box from what it
watches, own battery, always on. Alerts go to ntfy (account-free, ntfy
formats Alertmanager's JSON itself, no bridge).

```txt
 nothing phone 2 (monitor)                          poco f5 pro (services)
┌──────────────────────────────────────────┐        ┌──────────────────────────┐
│ prometheus :9090 ──► alertmanager :9093 ─┼─► ntfy │ node_exporter :9100      │
│   │  scrape                              │        │   textfile: battery.prom │
│   ├──► node_exporter :9100 (itself)      │        │ shoko :8111  mealprep    │
│   └──► blackbox :9115 ── http/tcp ───────┼───────►│ haproxy :8443  nfs :2049 │
└──────────────────────────────────────────┘        └──────────────────────────┘
```

Nagios → here: NRPE = `node_exporter` on each host; check_http/tcp/ssl =
`blackbox_exporter` from the monitor; service checks = rules in
`alerts.yml`; notification commands = Alertmanager receivers; `battery.sh` =
a custom check via the textfile collector.

## Layout

```txt
deploy/fetch.sh              downloads an upstream linux-arm64 build into ~/monitoring/bin
deploy/prometheus.yml        scrape targets: node on both phones, blackbox http/tcp
deploy/alerts.yml            rules: down, probe failed, cert < 14d, disk, thermal, swap, battery
deploy/alertmanager.yml      route everything to ntfy, drop Watchdog; topic url read from ~/monitoring/ntfy.url
deploy/blackbox.yml          http_2xx (follows redirects), tcp_connect
deploy/battery.sh            cron */1: termux-battery-status -> ~/monitoring/textfile/battery.prom
deploy/sv-*.run              runit services
```

On a phone, outside the repo: `~/monitoring/{bin,data,alertmanager,textfile}`,
`~/monitoring/ntfy.url` (secret, `https://ntfy.sh/<topic>?template=alertmanager`).

## Install

### Every phone (node_exporter + battery)

```sh
pkg install termux-services termux-api python    # termux-api needs the Termux:API app too
git clone https://github.com/sandravwc/monitoring ~/monitoring/repo
~/monitoring/repo/deploy/fetch.sh node_exporter
mkdir -p ~/monitoring/textfile $PREFIX/var/service/node-exporter
cp ~/monitoring/repo/deploy/sv-node-exporter.run $PREFIX/var/service/node-exporter/run
export SVDIR=$PREFIX/var/service; sv up node-exporter
(crontab -l 2>/dev/null; echo '* * * * * $HOME/monitoring/repo/deploy/battery.sh') | crontab -
curl -s localhost:9100/metrics | grep -E '^termux_battery|^node_thermal' | head
```

Net collectors are off: Android denies netlink and `/proc/net` to apps, they
would only log errors. `/data` is the filesystem that matters; the exclude
list hides Android's 30 pseudo mounts.

### Monitor (Nothing)

```sh
for c in prometheus alertmanager blackbox_exporter; do ~/monitoring/repo/deploy/fetch.sh $c; done
echo 'https://ntfy.sh/<topic>?template=alertmanager' > ~/monitoring/ntfy.url; chmod 600 ~/monitoring/ntfy.url
for s in prometheus alertmanager blackbox; do mkdir -p $PREFIX/var/service/$s; cp ~/monitoring/repo/deploy/sv-$s.run $PREFIX/var/service/$s/run; done
sv up prometheus alertmanager blackbox
~/monitoring/bin/prometheus --config.file ~/monitoring/repo/deploy/prometheus.yml --check-config   # promtool is in the tarball too
```

Subscribe to the topic in the ntfy app. UIs (LAN only via ssh tunnel, they
bind 127.0.0.1): `ssh -L 9090:127.0.0.1:9090 nothing` → http://localhost:9090
(`/alerts`, `/targets`), 9093 for Alertmanager.

Test an alert without breaking anything:

```sh
~/monitoring/bin/amtool --alertmanager.url=http://127.0.0.1:9093 alert add test severity=warning host=nothing --annotation=summary="ntfy test"
```

## Operate

- Change a rule/target: edit in the workstation clone, push, `git pull` on the Nothing, `sv restart prometheus` (or `kill -HUP` for a config reload)
- Logs: `$PREFIX/var/log/sv/<svc>/current`
- Update a binary: `fetch.sh <name>`, `sv restart <svc>`
- Dead monitor: the `Watchdog` alert fires forever by design and is routed to a blackhole; if it ever stops arriving at Alertmanager (`/alerts` in the UI), Prometheus is down. Nothing external checks the monitor yet (todo: workstation cron)
- Data: 90 d retention, ~1 GB/yr at this size

## Gotchas

- `node_thermal_zone_temp` works (`/sys/class/thermal` readable), `hwmon` mostly not
- `termux-battery-status` current sign: negative = charging on Xiaomi kernels; `BatteryDraining` alert relies on it
- HyperOS kills Termux when idle: `termux-wake-lock` + battery optimization off for Termux on every phone, or the monitor itself vanishes
