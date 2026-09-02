# CodeDeploy 훅 권한 불일치로 인한 시크릿 치환 실패

- **발생일**: 2026-09-02
- **영역**: 배포 (AWS CodeDeploy + GitHub Actions)
- **관련 파일**: `appspec.yml`, `deploy/after_install.sh`, `deploy/replace_secret.py`, `apis/seoul_data/realtime_bicycle.py`

> 호스트명, S3 버킷명, CodeDeploy 애플리케이션명은 마스킹했다.
> 경로와 uid 는 재현에 필요하므로 실제 값을 남긴다.

## 요약

- **증상**: EC2 에서 API 호출 시 `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`
- **원인**: `appspec.yml` 의 `permissions.owner`(ubuntu)와 `hooks.runas`(kafka)가 어긋나 시크릿 치환 스크립트가 `PermissionError` 로 죽었으나, `set -e` 부재로 배포는 성공 처리됨
- **수정**: 소유자와 실행 유저 일치, `set -e` 추가, 치환 실패 시 non-zero 종료

## 증상

EC2 에서 실행 시 아래 로그가 30초 간격으로 무한 반복되었다.

```
2026-09-02 18:37:07,144 [ERROR]:요청 실패, Traceback (most recent call last):
  File "/src/kafka-producer/apis/seoul_data/realtime_bicycle.py", line 30, in call
    contents = json.loads(rslt.text)
  File "/usr/lib/python3.10/json/__init__.py", line 346, in loads
    return _default_decoder.decode(s)
  File "/usr/lib/python3.10/json/decoder.py", line 337, in decode
    obj, end = self.raw_decode(s, idx=_w(s, 0).end())
  File "/usr/lib/python3.10/json/decoder.py", line 355, in raw_decode
    raise JSONDecodeError("Expecting value", s, err.value) from None
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

`char 0` 에서의 파싱 실패는 **응답이 JSON 이 아니라는 뜻**이다. HTML 이거나 빈 문자열이다.
그런데 코드가 `rslt.status_code` 도 `rslt.text` 도 남기지 않아 무엇을 받았는지 알 수 없었다.
이것이 추적이 길어진 첫 번째 이유다.

## 원인 사슬

증상과 원인이 다섯 단계 떨어져 있고, 중간에서 아무도 소리를 내지 않았다.

```
appspec.yml: owner ubuntu, mode 755 ─┐
appspec.yml: runas kafka            ─┴→ 훅 실행 중 PermissionError
                                          |
                       replace_secret.py 실패 (exit 1)
                                          |
        after_install.sh 에 set -e 없음 → 훅 종료코드는 마지막 명령의 것 → 0
                                          |
                          CodeDeploy 콘솔에 "배포 성공"
                                          |
             소스에 ##auth_key_seoul_data## 플레이스홀더 잔존
                                          |
                '#' 이 URL fragment 로 해석되어 경로가 잘림
                                          |
       실제 요청은 http://openapi.seoul.go.kr:8088/ 루트로 나감 → HTML 응답
                                          |
                      JSONDecodeError (실행 시점, 배포 훨씬 이후)
```

## 추적 과정

### 가설 A. 인증키가 무효하다

가장 먼저 의심한 것. `config/application.yml` 의 치환 여부부터 확인했다.

```bash
grep -c '##auth_key_seoul_data##' /src/kafka-producer/config/application.yml
# → 0
```

`0` 이므로 GitHub Actions 의 sed 치환은 정상이었다. **가설 A 배제.**

다만 여기엔 함정이 있다. 시크릿이 비어 있어도 플레이스홀더는 사라지므로 `0` 이 나온다.
값의 존재까지 확인해야 완전하다.

```bash
python3 -c "
import yaml
v = yaml.safe_load(open('/src/kafka-producer/config/application.yml'))['api_key']['auth_key_seoul_data']
print('type:', type(v).__name__, '| len:', len(v) if v else v)
"
```

`type: NoneType` 이 나온다면 시크릿이 비었거나, 치환 전 상태에서 YAML 이 `##` 이후를
주석으로 먹은 것이다. (`key: ##value##` 는 YAML 에서 값이 `None` 이 된다.)

### 가설 B. EC2 아웃바운드에서 8088 포트가 막혔다

`curl` 이 아무것도 출력하지 않아 잠시 의심했으나, 이는 `curl -s` 가 에러 메시지까지
삼킨 탓이었다. `-sS` 와 `-w` 를 붙이면 드러난다.

```bash
curl -sS -o /tmp/b.txt \
  -w 'HTTP %{http_code} | %{content_type} | %{size_download}B\nURL: %{url_effective}\n' \
  "http://openapi.seoul.go.kr:8088/sample/json/bikeList/1/5"
```

서울열린데이터광장은 `sample` 을 테스트 인증키로 지원한다. 인증을 배제한 채
연결과 URL 형식만 검증할 수 있어 유용하다. **가설 B 배제.**

### 가설 C. 소스 파일에는 치환이 반영되지 않았다

`config/application.yml` 은 멀쩡한데 소스는 어떤지 확인했다. 이것이 결정타였다.

```bash
grep -n 'self.auth_key' /src/kafka-producer/apis/seoul_data/realtime_bicycle.py
# 14:        self.auth_key = "##auth_key_seoul_data##"
```

플레이스홀더가 그대로 남아 있었다. 길이로도 교차 검증된다.

```bash
KEY=$(sed -n 's/.*self\.auth_key = "\(.*\)".*/\1/p' \
  /src/kafka-producer/apis/seoul_data/realtime_bicycle.py)
echo "len=${#KEY}"
# → len=23   ("##auth_key_seoul_data##" 가 정확히 23자)
```

`config/application.yml` → 소스로 값을 옮기는 `deploy/replace_secret.py` 가 실패한 것이다.
**가설 C 확진.**

여기서 `#` 의 동작을 확인해두면 증상이 완전히 설명된다.

```bash
python3 -c "
from urllib.parse import urlsplit
print(urlsplit('http://openapi.seoul.go.kr:8088/##auth_key_seoul_data##/json/bikeList/1/1000'))
"
# path='/' fragment='#auth_key_seoul_data##/json/bikeList/1/1000'
```

`#` 는 URL fragment 구분자다. `requests` 는 fragment 를 서버로 보내지 않으므로
실제 요청은 루트 경로로 나가고, 돌아온 HTML 을 `json.loads` 가 파싱하다 `char 0` 에서 터진다.

### 가설 D. replace_secret.py 는 왜 실패했나

훅과 동일한 유저(`kafka`)로 직접 실행해 재현했다.

```
kafka@broker-host:~$ python3 /src/kafka-producer/deploy/replace_secret.py; echo "exit=$?"
Traceback (most recent call last):
  File "/src/kafka-producer/deploy/replace_secret.py", line 25, in <module>
    with open(f"{root}/{file}", "w", encoding="utf-8") as file_write:
PermissionError: [Errno 13] Permission denied: '/src/kafka-producer/deploy/replace_secret.py'
exit=1
```

권한 상태를 확인했다.

```
kafka@broker-host:~$ ls -ld /src/kafka-producer/apis/seoul_data; id
drwxr-xr-x 2 ubuntu ubuntu 4096 Sep  2 18:59 /src/kafka-producer/apis/seoul_data
uid=1001(kafka) gid=1001(kafka) groups=1001(kafka),1000(ubuntu)
```

**가설 D 확진.**

## 원인

`mode 755` 를 풀어보면 kafka 가 쓰기에 닿을 경로가 없다.

| 대상 | 권한 | kafka 에게 적용되는가 |
|---|---|---|
| owner (`ubuntu`) | `rwx` | 아니오 — kafka 는 소유자가 아님 |
| group (`ubuntu`) | `r-x` | 예 — kafka 가 ubuntu 그룹 소속이라 여기 걸림 |
| other | `r-x` | — |

kafka 는 `groups=...,1000(ubuntu)` 로 ubuntu 그룹에 속하지만 **group 비트에 `w` 가 없다.**
설령 그룹에 속하지 않았더라도 other 가 `r-x` 라 결과는 같다.
`replace_secret.py` 는 소스 파일을 `open(..., "w")` 로 덮어쓰므로 항상 실패한다.

문제의 `appspec.yml` 은 이렇게 되어 있었다.

```yaml
permissions:
  - object: /src/kafka-producer
    owner: ubuntu      # 파일은 ubuntu 소유로 만들고
    mode: 755
hooks:
  AfterInstall:
    - location: deploy/after_install.sh
      runas: kafka     # 훅은 kafka 로 실행
```

CodeDeploy 는 이 둘을 대조해주지 않는다. 시킨 대로 파일을 ubuntu 소유로 만들고 훅을 kafka 로 돌린다.

### 왜 배포는 성공으로 표시되었나

`deploy/after_install.sh` 가 이랬다.

```bash
source /src/kafka_venv/bin/activate
python3 /src/kafka-producer/deploy/replace_secret.py   # 여기서 죽음 (exit 1)
pip3 install -r /src/kafka-producer/requirements.txt   # 그래도 실행됨, exit 0
```

`set -e` 가 없으니 스크립트는 계속 진행하고, **셸 스크립트의 종료코드는 마지막 명령의 것**이다.
`pip3 install` 이 성공하니 훅 전체가 `0` 으로 끝나고 콘솔에는 초록불이 뜬다.
실제로는 시크릿 주입이 통째로 빠진 채 배포된 것이다.

### 참고: 튜토리얼에서는 왜 재현되지 않는가

`runas` 를 생략하면 훅은 **root** 로 실행된다. root 는 파일 권한 비트를 무시하므로
`owner: ubuntu` 와 조합해도 아무 문제 없이 통과한다. `runas` 를 명시하는 순간
소유자와의 정합성이 필요해지는데, 이 의존 관계는 어디에도 드러나지 않는다.

## 수정

| 파일 | 변경 내용 |
|---|---|
| `appspec.yml` | `permissions.owner`/`group` 을 `kafka` 로 변경해 `hooks.runas` 와 일치시킴 |
| `deploy/after_install.sh` | `set -euo pipefail` 추가. `pip3 install` 을 `replace_secret.py` **앞으로** 이동 (치환 스크립트가 PyYAML 에 의존하므로 기존 순서면 첫 배포에서 `ModuleNotFoundError`) |
| `deploy/replace_secret.py` | 값이 `None`/빈 문자열이거나 총 치환 건수가 0 이면 `sys.exit`. 치환할 내용이 없는 파일은 열지 않음. `write()` 가 안쪽 루프에 있어 설정 섹션이 2개 이상이면 파일 내용이 중복 기록되던 버그 수정. 디렉토리 제외를 문자열 검사에서 `dirs[:]` 필터로 교체 (기존 `root.find("/config/") > 0` 는 트레일링 슬래시가 없어 실제로 제외되지 않았음) |
| `apis/seoul_data/realtime_bicycle.py` | `requests.get(url, headers)` → `headers=headers` (두 번째 위치 인자는 `params` 라 헤더가 쿼리스트링으로 나가고 있었음). 실패 시 `status_code` 와 응답 본문 앞 200자 로깅. 생성자에서 인증키에 `#` 가 있으면 즉시 `RuntimeError`. `MAX_RETRY` 도입 (기존엔 `while True` 무한 재시도). `CODE` 에러 응답이 파싱 로직으로 흘러가 다시 터지던 흐름을 `continue` 로 수정. 모듈 최상단 실행 코드를 `if __name__ == "__main__":` 안으로 |
| `.github/workflows/master.yml` | `sed -ie` 는 `application.ymle` 백업 파일을 만들어 `tar cvfz ... *` 에 딸려 들어가고, 키에 `/` 나 `&` 가 있으면 치환이 깨진다(`&` 는 매치 문자열로 확장됨). python 치환으로 교체하고 시크릿이 비었거나 플레이스홀더를 못 찾으면 워크플로 실패 처리 |

수정 후에는 첫 단계에서 멈춘다. 권한이 안 맞으면 `set -e` 가 배포를 실패로 표시하고,
그래도 뚫고 나가면 `replace_secret.py` 가 치환 0건으로 종료하며,
그마저 통과하면 `RealtimeBicycle` 생성자가 `#` 를 보고 예외를 던진다.

## 재사용 가능한 진단 명령어

```bash
# 플레이스홀더 치환 여부 (1 이면 미치환)
grep -c '##placeholder##' <file>

# 값이 실제로 존재하는지 (치환됐어도 빈 값일 수 있음)
python3 -c "import yaml; v=yaml.safe_load(open('<yml>'))['<section>']['<key>']; print(type(v).__name__, len(v) if v else v)"

# 요청이 실제로 어디로 나가는지 — '#' 잘림 감지에 유효
curl -sS -o /tmp/b.txt -w 'HTTP %{http_code} | %{content_type} | %{size_download}B\nURL: %{url_effective}\n' "<url>"

# 인증을 배제한 연결 테스트 (서울열린데이터광장 한정)
curl -sS "http://openapi.seoul.go.kr:8088/sample/json/bikeList/1/5"

# 배포 훅과 동일한 조건으로 재현
sudo -u <runas유저> <명령>

# CodeDeploy 훅이 실제로 남긴 출력
sudo tail -n 200 /opt/codedeploy-agent/deployment-root/deployment-logs/codedeploy-agent-deployments.log

# URL 에서 fragment 가 잘리는지 확인
python3 -c "from urllib.parse import urlsplit; print(urlsplit('<url>'))"
```

## 교훈

- **`appspec.yml` 에서 `permissions.owner` 와 `hooks.runas` 는 반드시 함께 본다.**
  CodeDeploy 는 둘의 정합성을 검사해주지 않는다. `runas` 를 생략하면 root 로 실행되어
  권한 문제가 드러나지 않으므로, `runas` 를 명시하는 순간 소유자를 같이 확인해야 한다.
- **배포 훅 스크립트에는 `set -euo pipefail` 을 반드시 넣는다.**
  셸 스크립트의 종료코드는 마지막 명령의 것이므로, 중간 실패가 성공으로 둔갑한다.
  "배포 성공" 은 "훅의 모든 단계가 성공" 을 의미하지 않는다.
- **URL 에 들어가는 값에 `#` 가 섞이면 조용히 잘린다.** 치환되지 않은 플레이스홀더가
  `##...##` 형태라면 특히 위험하다. 에러 대신 엉뚱한 응답이 돌아와 원인 추적이 어려워진다.
- **파싱 실패 시 원본 응답을 로깅한다.** `status_code` 와 본문 앞부분만 남겼어도
  추적이 몇 단계 짧아졌을 것이다.
- **`curl -s` 는 에러까지 삼킨다.** 진단할 때는 `-sS` 와 `-w` 를 쓴다.
- **YAML 에서 `key: ##value##` 는 값이 `None` 이다.** `#` 이후가 주석으로 처리된다.
- **의존성 설치 순서를 확인한다.** 배포 스크립트가 라이브러리를 쓴다면 그 설치가
  선행되어야 한다. 이번 건에서는 권한 문제가 먼저 터져 가려져 있었을 뿐이다.
