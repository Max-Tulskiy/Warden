#!/bin/sh
# Stops and disables the service before its unit file is removed, so an
# uninstall does not leave a running process pointing at a deleted binary.
set -e

systemctl stop warden-agent 2>/dev/null || true
systemctl disable warden-agent 2>/dev/null || true
