#!/bin/sh
# Reloads the unit file and, on a fresh install (not an upgrade), points
# the administrator at the one manual step packaging cannot do for them:
# filling in server_url and enrollment_token before the service can start.
set -e

systemctl daemon-reload || true

if [ "$1" = "1" ] || [ "$1" = "configure" ]; then
    echo "Warden agent installed. Edit /etc/warden-agent/config.toml"
    echo "(server_url and enrollment_token), then run:"
    echo "  systemctl enable --now warden-agent"
fi
