#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu 24.04 droplet. Run as root:
#   curl -fsSL https://raw.githubusercontent.com/bkratko/Instant-Refund/main/scripts/bootstrap.sh | bash
set -euo pipefail
REPO=https://github.com/bkratko/Instant-Refund.git
DIR=/opt/instant-refund

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
apt-get install -y -qq git ufw >/dev/null
ufw allow OpenSSH >/dev/null && ufw allow 80/tcp >/dev/null && ufw allow 16211/tcp >/dev/null && ufw --force enable >/dev/null

[ -d "$DIR/.git" ] || git clone -q "$REPO" "$DIR"
cd "$DIR" && git pull -q

if [ ! -f .env ]; then
  rand() { openssl rand -hex "$1"; }
  cat > .env <<ENV
KASPA_NETWORK=testnet-10
KASPA_EXPECTED_FROM_ADDRESS=
KASPA_CONFIRMATIONS_REQUIRED=10
POSTGRES_PASSWORD=$(rand 24)
SIGNER_SHARED_SECRET=$(rand 32)
API_KEYS=$(rand 24)
DEMO_MODE=true
CORS_ORIGINS=
RATE_LIMIT=300/minute
ENV
  chmod 600 .env
fi

./scripts/keygen.sh
docker compose up -d --build
echo
echo "Stack is starting. kaspad needs time to sync testnet before anchors confirm."
echo "Settlement address (fund it from a testnet faucet):"
grep KASPA_EXPECTED_FROM_ADDRESS .env | cut -d= -f2
echo "API key for merchants: $(grep ^API_KEYS .env | cut -d= -f2)"
