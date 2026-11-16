#!/bin/sh
set -e

cp /deployment/config/config.env /app/.env
cp /deployment/config/beeflow.yaml /app/config/beeflow.yaml
cp /deployment/config/kafka.yaml /app/config/kafka.yaml

exec supervisord -n -c /etc/supervisor/supervisord.conf
