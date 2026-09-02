# 삽질 기록 (Troubleshooting)

원인을 찾는 데 시간을 쓴 문제를 기록한다. 결론만 남기지 않고 **틀린 가설과 그것을
배제한 방법까지** 남기는 것이 목적이다. 다음에 같은 증상을 만났을 때 추적 경로를
그대로 다시 밟을 수 있어야 값어치가 있다.

## 작성 규칙

- 파일명은 `<영역>-<핵심 원인>.md`. 날짜는 파일명에 넣지 않고 문서 상단 메타데이터로 둔다.
  검색해서 찾아오는 사람은 "언제"가 아니라 "무슨 증상"으로 찾는다.
- 증상은 **로그 원문 그대로** 붙인다. 요약하면 검색에 걸리지 않는다.
- 확인에 사용한 명령어를 그대로 남긴다. 재현 가능해야 한다.
- 배제한 가설도 남긴다. 보통 이 부분이 제일 쓸모 있다.
- 호스트명, 버킷명, 계정 식별자는 마스킹한다. 단 경로나 uid 처럼 재현에 필요한
  값까지 지우면 문서가 무의미해지므로 남긴다.

## 문서 목록

### 배포 / CodeDeploy

| 문서 | 한 줄 요약 |
|---|---|
| [CodeDeploy 훅 권한 불일치로 인한 시크릿 치환 실패](codedeploy-runas-permission.md) | `appspec.yml` 의 `owner` 와 `runas` 가 어긋나 훅이 실패했으나 배포는 성공으로 표시됨 |

## 증상으로 찾기

에러 메시지에서 거꾸로 찾아 들어가기 위한 역인덱스.

| 증상 / 에러 메시지 | 문서 |
|---|---|
| `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)` | [codedeploy-runas-permission](codedeploy-runas-permission.md) |
| `PermissionError: [Errno 13] Permission denied` (배포 훅 실행 중) | [codedeploy-runas-permission](codedeploy-runas-permission.md) |
| 배포는 성공인데 시크릿 플레이스홀더가 소스에 그대로 남아있음 | [codedeploy-runas-permission](codedeploy-runas-permission.md) |
| API 요청이 엉뚱하게 루트 경로로 나감 | [codedeploy-runas-permission](codedeploy-runas-permission.md) |
