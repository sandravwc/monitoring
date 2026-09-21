#!/data/data/com.termux/files/usr/bin/sh
# cron * * * * *. termux-battery-status -> node_exporter textfile collector. current: negative = into the battery on Xiaomi kernels.
out=$HOME/monitoring/textfile/battery.prom
termux-battery-status | python3 -c '
import json,sys
b=json.load(sys.stdin)
print("termux_battery_percent", b["percentage"])
print("termux_battery_current_amps", b["current"]/1e6)
print("termux_battery_temperature_celsius", b["temperature"])
print("termux_battery_plugged", 0 if b["plugged"]=="UNPLUGGED" else 1)
print("termux_battery_charging", 1 if b["status"]=="CHARGING" else 0)
' > $out.tmp && mv $out.tmp $out
