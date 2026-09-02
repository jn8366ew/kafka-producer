#!/bin/bash
# 훅 스크립트가 중간에 실패해도 마지막 명령의 종료코드만 반영되면
# CodeDeploy 가 배포를 성공으로 표시해버리므로 set -e 로 즉시 중단시킴
set -euo pipefail

ROOT_DIR="/src/kafka-producer"
VENV_DIR="/src/kafka_venv"

source "${VENV_DIR}/bin/activate"

# replace_secret.py 가 PyYAML 에 의존하므로 의존성 설치를 먼저 수행해야 함
pip3 install -r "${ROOT_DIR}/requirements.txt"

# 치환 실패 시 non-zero 로 종료되어 배포도 실패로 표시됨
python3 "${ROOT_DIR}/deploy/replace_secret.py"
