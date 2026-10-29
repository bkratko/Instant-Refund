#!/usr/bin/env bash
# Generate the settlement key ON the server (it never leaves it) and record its address in .env.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p secrets && chmod 711 secrets
if [ -f secrets/settlement.key ]; then
  echo "secrets/settlement.key already exists; keeping it."; exit 0
fi
docker compose build -q sidecar
NET=$(grep ^KASPA_NETWORK .env | cut -d= -f2)
ADDR=$(docker compose run --rm --no-deps -u 0 -v "$PWD/secrets:/out" -e KASPA_NETWORK="$NET" \
       --entrypoint sidecar-kaspa sidecar keygen /out/settlement.key | tail -1)
chown 10001 secrets/settlement.key && chmod 400 secrets/settlement.key
sed -i "s|^KASPA_EXPECTED_FROM_ADDRESS=.*|KASPA_EXPECTED_FROM_ADDRESS=$ADDR|" .env
echo "Settlement address: $ADDR"
