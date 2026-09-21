# monitoring

Prometheus + Alertmanager on the Poco, watching the Poco. Nagios shape
(checks, thresholds, pushes) with Go static binaries that run rootless in
Termux. Yes, the monitor sits on the box it monitors: the other phones are
daily drivers, the workstation sleeps. The one thing that setup cannot see, a
dead Poco, is covered by a cron on the workstation (`deadman.sh`). Alerts go
to ntfy (account-free, ntfy formats Alertmanager's JSON itself, no bridge).

```txt
 poco f5 pro                                                       workstation
┌────────────────────────────────────────────────────────┐        ┌─────────────────────┐
│ prometheus :9090 ──► alertmanager :9093 ──► ntfy.sh    │ ◄──ssh─┤ cron */30 deadman.sh│
│   │  scrape                                            │        │  ntfy if unreachable│
│   ├──► node_exporter :9100  (meminfo, /data, cpufreq,  │        └─────────────────────┘
│   │       textfile: battery + cpu thermal, cron */1)   │
│   └──► blackbox :9115 ── http/tcp ──► haproxy :8443 ──► anubis ──► shoko :8111 / mealprep :8090
│                                       nfs :2049, sshd :8022, syncthing :8384
└────────────────────────────────────────────────────────┘
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
deploy/deadman.sh            workstation cron: ntfy when the Poco's Prometheus is unreachable
```

On the Poco, outside the repo: `~/monitoring/{bin,data,alertmanager,textfile}`,
`~/monitoring/ntfy.url` (secret, `https://ntfy.sh/<topic>?template=alertmanager`).

## Install

### Poco: node_exporter + battery

```sh
pkg install termux-services termux-api python    # termux-api needs the Termux:API app too
git clone https://github.com/sandravwc/monitoring ~/monitoring/repo
~/monitoring/repo/deploy/fetch.sh node_exporter 1.8.2     # pinned, newer ones die with SIGSYS on Android
mkdir -p ~/monitoring/textfile $PREFIX/var/service/node-exporter
cp ~/monitoring/repo/deploy/sv-node-exporter.run $PREFIX/var/service/node-exporter/run
export SVDIR=$PREFIX/var/service; sv up node-exporter
(crontab -l 2>/dev/null; echo '* * * * * $HOME/monitoring/repo/deploy/battery.sh') | crontab -
curl -s localhost:9100/metrics | grep -E '^termux_' | head
```

Collectors are an allowlist, not the defaults. Android denies apps
`/proc/stat`, `/proc/loadavg`, `/proc/vmstat`, `/proc/net`, netlink and parts
of `/sys`: no CPU, load or network metrics on a phone, ever. What works:
meminfo, filesystem (`/data`), cpufreq, uname, time, textfile. Thermal comes
from `battery.sh` (the built-in collector fails on the first denied zone).
`/data` is the filesystem that matters; the exclude list hides Android's 30
pseudo mounts.

### Poco: Prometheus, Alertmanager, blackbox

```sh
for c in prometheus alertmanager blackbox_exporter; do ~/monitoring/repo/deploy/fetch.sh $c; done
echo 'https://ntfy.sh/<topic>?template=alertmanager' > ~/monitoring/ntfy.url; chmod 600 ~/monitoring/ntfy.url
for s in prometheus alertmanager blackbox; do mkdir -p $PREFIX/var/service/$s; cp ~/monitoring/repo/deploy/sv-$s.run $PREFIX/var/service/$s/run; done
sv up prometheus alertmanager blackbox
~/monitoring/bin/prometheus --config.file ~/monitoring/repo/deploy/prometheus.yml --check-config   # promtool is in the tarball too
```

Subscribe to the topic in the ntfy app. UIs (ssh tunnel, everything binds
127.0.0.1): `ssh -L 9090:127.0.0.1:9090 poco` → http://localhost:9090
(`/alerts`, `/targets`), 9093 for Alertmanager.

Test an alert without breaking anything:

```sh
~/monitoring/bin/amtool --alertmanager.url=http://127.0.0.1:9093 alert add test severity=warning host=nothing --annotation=summary="ntfy test"
```

## Operate

- Change a rule/target: edit in the workstation clone, push, `git pull` on the Nothing, `sv restart prometheus` (or `kill -HUP` for a config reload)
- Logs: `$PREFIX/var/log/sv/<svc>/current`
- Update a binary: `fetch.sh <name>`, `sv restart <svc>`
- Dead monitor: `deadman.sh` from the workstation cron, `*/30 * * * * ~/workdir/git/monitoring/deploy/deadman.sh`, topic url in `~/.config/monitoring-ntfy.url`. Only fires while the workstation is awake; the `Watchdog` alert (always firing, blackholed) shows in `/alerts` that rules evaluate
- Data: 90 d retention, ~1 GB/yr at this size

## Gotchas

- node_exporter ≥ 1.9 calls `open_tree()` (filepath-securejoin), Android seccomp answers SIGSYS, process dies on first scrape. 1.8.2 pinned
- `/sys/class/thermal`: cpu zones readable, others not; `hwmon`, `pressure` denied
- `termux-battery-status` current sign: negative = charging on Xiaomi kernels; `BatteryDraining` alert relies on it
- HyperOS kills Termux when idle: `termux-wake-lock` + battery optimization off for Termux, or the monitor vanishes with everything else (that is what `deadman.sh` is for)
