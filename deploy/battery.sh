#!/data/data/com.termux/files/usr/bin/sh
# cron * * * * *. termux-battery-status + cpu thermal zones -> node_exporter textfile collector.
# current: negative = into the battery on Xiaomi kernels. thermal_zone collector can't be used: one denied zone fails the whole collector.
out=$HOME/monitoring/textfile/battery.prom
termux-battery-status | python3 -c '
import json,sys
b=json.load(sys.stdin)
print("termux_battery_percent", b["percentage"])
print("termux_battery_current_amps", b["current"]/1e6)
print("termux_battery_temperature_celsius", b["temperature"])
print("termux_battery_plugged", 0 if b["plugged"]=="UNPLUGGED" else 1)
print("termux_battery_charging", 1 if b["status"]=="CHARGING" else 0)
' > $out.tmp
for z in /sys/class/thermal/thermal_zone*; do
    t=$(cat $z/type 2>/dev/null) || continue
    case "$t" in cpu*) v=$(cat $z/temp 2>/dev/null) || continue; echo "termux_cpu_temperature_celsius{zone=\"$t\"} $(echo "$v / 1000" | bc -l | cut -c1-5)" >> $out.tmp;; esac
done
mv $out.tmp $out
