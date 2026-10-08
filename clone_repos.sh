#!/usr/bin/env bash
# Необязательно: полные архивы TDP/постеров RCJ и индекс awesome-rcj-soccer.
# Клонирует репозитории в _repos/ и удаляет .git, чтобы их можно было закоммитить в вашу библиотеку.
set -euo pipefail
mkdir -p _repos && cd _repos
for r in rcj-eu-soccer-tdp-2026 rcj-soccer-tdp-2026 rcj-soccer-tdp-2025 awesome-rcj-soccer ir-golf-ball soccer-communication-module; do
  [[ -d "$r" ]] && { echo "skip $r"; continue; }
  git clone --depth 1 "https://github.com/robocup-junior/$r" "$r"
  rm -rf "$r/.git"
done
echo "Готово. Папка _repos/ содержит полные копии репозиториев."
