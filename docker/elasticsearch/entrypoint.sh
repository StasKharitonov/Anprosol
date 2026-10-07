#!/bin/bash
set -euo pipefail

args=()
for key in \
  discovery.type \
  network.host \
  http.host \
  xpack.security.enabled \
  xpack.security.enrollment.enabled \
  xpack.security.http.ssl.enabled \
  xpack.ml.enabled \
  ingest.geoip.downloader.enabled \
  cluster.routing.allocation.disk.threshold_enabled
do
  value="$(printenv "$key" || true)"
  if [ -z "$value" ]; then
    case "$key" in
      discovery.type) value="single-node" ;;
      network.host|http.host) value="0.0.0.0" ;;
      xpack.security.enabled|xpack.security.enrollment.enabled|xpack.security.http.ssl.enabled|xpack.ml.enabled|ingest.geoip.downloader.enabled|cluster.routing.allocation.disk.threshold_enabled)
        value="false"
        ;;
    esac
  fi
  args+=(-E "${key}=${value}")
done

exec /usr/share/elasticsearch/bin/elasticsearch "${args[@]}"
