#!/bin/bash
# CodeDeploy AfterInstall 훅.
# shebang 이 없으면 sh 로 실행되어 `source` 가 동작하지 않으므로 반드시 필요하다.
set -euo pipefail

APP_DIR=/src/kafka-producer
VENV_DIR=/src/kafka_venv

echo "[after_install] 시작 (user=$(whoami))"

# venv 가 없으면 생성. Ubuntu 는 python3-venv 패키지가 따로 필요할 수 있음
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "[after_install] venv 생성: $VENV_DIR"
  mkdir -p "$(dirname "$VENV_DIR")"
  if ! python3 -m venv "$VENV_DIR"; then
    echo "[after_install] python3-venv 설치 후 재시도"
    apt-get update -y
    apt-get install -y python3-venv
    python3 -m venv "$VENV_DIR"
  fi
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r "$APP_DIR/requirements.txt"

# 배포 파일 소유자(ubuntu)와 맞춰 둠
chown -R ubuntu:ubuntu "$VENV_DIR"

echo "[after_install] 설치 완료"
python -m pip show confluent-kafka | head -2
