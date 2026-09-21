#!/data/data/com.termux/files/usr/bin/sh
# cron * * * * *. What node_exporter can't get on Android, written for its textfile collector:
#  battery (termux-battery-status), cpu thermal zones, load via sysinfo() (no /proc/loadavg), cpu idle via cpuidle sysfs (no /proc/stat).
# current: negative = into the battery on Xiaomi kernels.
out=$HOME/monitoring/textfile/termux.prom
{
termux-battery-status | python3 -c '
import json, sys, ctypes, glob, os
b = json.load(sys.stdin)
print("termux_battery_percent", b["percentage"])
print("termux_battery_current_amps", b["current"] / 1e6)
print("termux_battery_temperature_celsius", b["temperature"])
print("termux_battery_plugged", 0 if b["plugged"] == "UNPLUGGED" else 1)
print("termux_battery_charging", 1 if b["status"] == "CHARGING" else 0)

class Sysinfo(ctypes.Structure):
    _fields_ = [("uptime", ctypes.c_long), ("loads", ctypes.c_ulong * 3), ("_rest", ctypes.c_byte * 256)]
si = Sysinfo(); ctypes.CDLL(None).sysinfo(ctypes.byref(si))
for n, v in zip(("1", "5", "15"), si.loads):
    print(f"termux_load{n}", round(v / 65536, 2))
print("termux_boot_time_seconds", si.uptime)

# busy = 1 - d(idle)/d(wall) since the previous run. Computed here, not with rate(): the file changes once a
# minute while prometheus scrapes twice a minute, so rate() over the plateaus under-counts idle.
import time, json as j
state = os.path.expanduser("~/monitoring/textfile/.cpuidle.json")
now = time.clock_gettime(time.CLOCK_BOOTTIME)
try: prev = j.load(open(state))
except Exception: prev = {}
cur = {}
for cpu in sorted(glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpuidle")):
    n = cpu.split("/")[-2][3:]; idle = 0
    for f in glob.glob(cpu + "/state*/time"):
        try: idle += int(open(f).read()) / 1e6
        except OSError: pass
    cur[n] = idle
    print("termux_cpu_idle_seconds_total{cpu=\"%s\"} %s" % (n, idle))
    if n in prev and now > prev["t"]:
        busy = max(0.0, min(1.0, 1 - (idle - prev[n]) / (now - prev["t"])))
        print("termux_cpu_busy_ratio{cpu=\"%s\"} %.3f" % (n, busy))
cur["t"] = now; j.dump(cur, open(state, "w"))
'
for z in /sys/class/thermal/thermal_zone*; do
    t=$(cat $z/type 2>/dev/null) || continue
    case "$t" in cpu*) v=$(cat $z/temp 2>/dev/null) || continue; echo "termux_cpu_temperature_celsius{zone=\"$t\"} $(echo "$v / 1000" | bc -l | cut -c1-5)";; esac
done
} > $out.tmp && mv $out.tmp $out
