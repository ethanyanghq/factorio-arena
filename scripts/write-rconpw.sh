#!/usr/bin/env bash
# Write the RCON password from .env into the file the Factorio image reads.
# The image generates a random password when docker/config/rconpw is missing; we want ours.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
	echo "error: .env not found; copy .env.example to .env and set FACTORIO_RCON_PASSWORD" >&2
	exit 1
fi
password=$(grep -E '^FACTORIO_RCON_PASSWORD=' .env | cut -d= -f2-)
if [[ -z "$password" || "$password" == "change-me" ]]; then
	echo "error: FACTORIO_RCON_PASSWORD in .env is empty or still 'change-me'" >&2
	exit 1
fi
umask 077
printf '%s' "$password" > docker/config/rconpw
