#!/bin/sh
# Workstation cron (*/30): the only eye outside the Poco. Pushes to ntfy when the monitor itself is unreachable.
# Prometheus binds 127.0.0.1 on the Poco, so the check goes over ssh. Needs the same topic url as ~/monitoring/ntfy.url, in ~/.config/monitoring-ntfy.url here.
ssh -o BatchMode=yes -o ConnectTimeout=10 poco_f5_pro-phone-hyperos 'curl -sf -m 5 http://127.0.0.1:9090/-/healthy' >/dev/null 2>&1 && exit 0
curl -s -H "Title: poco monitor unreachable" -H "Priority: high" -d "prometheus on the poco not answering (phone dead? termux killed?)" "$(sed 's/?.*//' ~/.config/monitoring-ntfy.url)" >/dev/null
