import os
import sys

import yaml

ROOT_DIR = "/src/kafka-producer"
CONFIG_PATH = os.path.join(ROOT_DIR, "config", "application.yml")

# 치환 대상에서 제외할 디렉토리
EXCLUDE_DIRS = {".git", ".github", "config", "venv", "__pycache__"}


def load_secrets(path):
    with open(path, "r", encoding="utf-8") as config:
        all_conf_dict = yaml.safe_load(config)

    secrets = {}
    for section, conf_item_dict in (all_conf_dict or {}).items():
        for k, v in (conf_item_dict or {}).items():
            # 값이 비어있으면 Actions 의 치환 단계가 실패했거나
            # '##...##' 가 YAML 주석으로 먹힌 것이므로 즉시 중단
            if v is None or not str(v).strip():
                sys.exit(
                    f"[replace_secret] '{section}.{k}' 값이 비어있음. "
                    f"GitHub Secret 등록 여부와 {path} 를 확인할 것"
                )
            secrets[k] = str(v)

    if not secrets:
        sys.exit(f"[replace_secret] {path} 에서 읽어들인 키가 없음")
    return secrets


def replace_in_file(path, secrets):
    with open(path, "r", encoding="utf-8") as file_read:
        original = file_read.read()

    replaced = original
    cnt = 0
    for k, v in secrets.items():
        placeholder = f"##{k}##"
        cnt += replaced.count(placeholder)
        replaced = replaced.replace(placeholder, v)

    # 치환할 내용이 없으면 파일을 열지 않음 (불필요한 쓰기·권한 오류 방지)
    if cnt == 0:
        return 0

    with open(path, "w", encoding="utf-8") as file_write:
        file_write.write(replaced)
    return cnt


def main():
    secrets = load_secrets(CONFIG_PATH)

    total = 0
    for root, dirs, files in os.walk(ROOT_DIR):
        # os.walk 순회 중 dirs 를 직접 수정하면 해당 디렉토리로 내려가지 않음
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        # 치환 대상은 .py 파일만 대상으로 함
        for file in files:
            if not file.endswith(".py"):
                continue
            path = os.path.join(root, file)
            cnt = replace_in_file(path, secrets)
            if cnt:
                print(f"[replace_secret] {path}: {cnt}건 치환")
                total += cnt

    # 한 건도 치환하지 못했다면 배포 결과가 잘못된 것이므로 실패 처리
    if total == 0:
        sys.exit(
            "[replace_secret] 치환된 항목이 없음. "
            "플레이스홀더 이름과 배포된 소스를 확인할 것"
        )
    print(f"[replace_secret] 총 {total}건 치환 완료")


if __name__ == "__main__":
    main()
