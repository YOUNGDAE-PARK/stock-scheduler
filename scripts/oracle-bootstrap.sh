#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

sudo systemctl enable --now docker
sudo usermod -aG docker "$USER" || true
sudo mkdir -p /opt/stock_scheduler
sudo chown -R "$USER:$USER" /opt/stock_scheduler

sudo iptables -C INPUT -p tcp -m state --state NEW -m tcp --dport 5173 -j ACCEPT 2>/dev/null \
  || sudo iptables -I INPUT 5 -p tcp -m state --state NEW -m tcp --dport 5173 -j ACCEPT
sudo iptables -C INPUT -p tcp -m state --state NEW -m tcp --dport 8000 -j ACCEPT 2>/dev/null \
  || sudo iptables -I INPUT 5 -p tcp -m state --state NEW -m tcp --dport 8000 -j ACCEPT
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent netfilter-persistent
sudo netfilter-persistent save

echo "Oracle VM bootstrap complete. Log out and back in if docker requires group refresh."
