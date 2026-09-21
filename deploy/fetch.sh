#!/data/data/com.termux/files/usr/bin/sh
# Download upstream linux-arm64 static builds into ~/monitoring/bin. No Termux packages for these.
# usage: fetch.sh prometheus|alertmanager|node_exporter|blackbox_exporter [version]
set -e
name=$1; ver=${2:-$(curl -s https://api.github.com/repos/prometheus/$name/releases/latest | grep -m1 '"tag_name"' | cut -d'"' -f4 | tr -d v)}
dir=$name-$ver.linux-arm64
mkdir -p $HOME/monitoring/bin && cd $HOME/monitoring/bin
curl -sL https://github.com/prometheus/$name/releases/download/v$ver/$dir.tar.gz | tar xz --strip-components=1 $dir/$name
./$name --version 2>&1 | head -1
