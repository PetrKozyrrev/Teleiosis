#!/bin/sh
# Explicit provisioning for the agreed empty Ubuntu 24.04 test server.
# Does not change SSH, firewall, existing services, or application secrets.
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo 'Run as root on the agreed test server.' >&2
    exit 1
fi
. /etc/os-release
if [ "$ID" != ubuntu ] || [ "$VERSION_ID" != 24.04 ]; then
    echo 'This bootstrap is intended only for Ubuntu 24.04.' >&2
    exit 1
fi
if command -v docker >/dev/null 2>&1; then
    docker version --format '{{.Server.Version}}'
    docker compose version
    echo 'Docker already exists; no package or service changes made.'
    exit 0
fi
for package in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
    if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q '^install ok installed$'; then
        echo "Conflicting package $package exists; review manually, no automatic removal." >&2
        exit 1
    fi
done
if [ -e /etc/apt/sources.list.d/docker.sources ] || [ -e /etc/apt/keyrings/docker.asc ]; then
    echo 'Existing Docker repository/key requires manual review; refusing overwrite.' >&2
    exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl
install -d -m 0755 /etc/apt/keyrings
curl --proto '=https' --tlsv1.2 --fail --silent --show-error \
    https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod 0644 /etc/apt/keyrings/docker.asc
architecture=$(dpkg --print-architecture)
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $architecture
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker version --format '{{.Server.Version}}'
docker compose version
echo 'Docker installed. No application or public proxy has been started.'
