import requests
import json
from json.decoder import JSONDecodeError
import logging
from logging.handlers import TimedRotatingFileHandler
import time
import os
import traceback


class RealtimeBicycle:

    MAX_RETRY = 3  # 동일 구간 연속 재시도 최대 횟수
    RETRY_WAIT = 30  # 재시도 전 대기 시간(초)
    TIMEOUT = 10  # 요청 타임아웃(초)

    def __init__(self, dataset_nm):
        self.auth_key = "##auth_key_seoul_data##"
        self.api_url = "http://openapi.seoul.go.kr:8088"
        self.log_dir = "/log/seoul_api"
        self.dataset_nm = dataset_nm
        self.chk_dir()
        self.log = self._get_logger()
        self._chk_auth_key()

    def _chk_auth_key(self):
        # 치환되지 않은 플레이스홀더가 남아있으면 '#' 이 URL fragment 로 해석되어
        # 요청이 루트 경로로 나가고 HTML 을 응답받는다. 원인 추적이 어려우므로 선제 차단
        if "#" in self.auth_key:
            raise RuntimeError(
                f"인증키가 치환되지 않음: {self.auth_key} "
                f"(deploy/replace_secret.py 실행 결과 확인 필요)"
            )

    def call(self):
        # url 형태: http://openapi.seoul.go.kr:8088/(인증키)/json/bikeList/1/5/
        base_url = f"{self.api_url}/{self.auth_key}/json/{self.dataset_nm}"
        start = 1
        end = 1000
        total_rows = []
        retry = 0
        while True:
            rslt = None
            try:
                rslt = self._call_api(base_url, start, end)
                contents = json.loads(rslt.text)
            except (JSONDecodeError, requests.RequestException):
                retry += 1
                # 응답 본문을 함께 남겨야 인증키/네트워크/응답형식 중 무엇이 문제인지 구분 가능
                status = rslt.status_code if rslt is not None else "N/A"
                body = repr(rslt.text[:200]) if rslt is not None else "N/A"
                self.log.error(
                    f"요청 실패({retry}/{self.MAX_RETRY}), status: {status}, "
                    f"body: {body}, {traceback.format_exc()}"
                )
                if retry >= self.MAX_RETRY:
                    raise RuntimeError(f"{self.MAX_RETRY}회 연속 요청 실패, 중단")
                time.sleep(self.RETRY_WAIT)
                continue

            # 정상이 아닌 경우 처리
            rslt_code = contents.get("CODE")
            if rslt_code:
                # INFO-200: 해당하는 데이터 없음. total_rows 리스트에 값이 존재할 경우
                # 조회 범위 초과로 에러 발생한 것이며 결과 리턴하고 종료
                if rslt_code == "INFO-200" and total_rows:
                    return total_rows

                retry += 1
                rslt_msg = contents.get("MESSAGE")
                self.log.error(
                    f"요청 실패({retry}/{self.MAX_RETRY}), "
                    f"에러코드: {rslt_code}, 메시지: {rslt_msg}"
                )
                if retry >= self.MAX_RETRY:
                    raise RuntimeError(
                        f"API 에러 응답, 에러코드: {rslt_code}, 메시지: {rslt_msg}"
                    )
                time.sleep(self.RETRY_WAIT)
                # 에러 응답을 아래 파싱 로직으로 흘려보내면 KeyError 로 다시 터지므로 재시도
                continue

            retry = 0  # 정상 응답을 받았으므로 재시도 카운트 초기화

            key_nm = list(contents.keys())[0]
            items = contents.get(key_nm)
            item_cnt = items.get("list_total_count")
            item_row = items.get("row")
            self.log.info(f"{base_url}/{start}/{end} 조회 성공, 건수: {len(item_row)}")
            if item_row:
                total_rows += item_row
            if item_cnt < 1000:
                break
            else:
                start = end + 1
                end += 1000
        return total_rows

    def _call_api(self, base_url, start, end, base_dt=""):
        headers = {
            "Content-Type": "application/json",
            "charset": "utf-8",
            "Accept": "*/*",
        }
        if len(base_dt) > 0:
            url = f"{base_url}/{start}/{end}/{base_dt}"
        else:
            url = f"{base_url}/{start}/{end}"
        # requests.get 의 두 번째 위치 인자는 params 이므로 headers 는 키워드로 전달해야 함
        rslt = requests.get(url, headers=headers, timeout=self.TIMEOUT)
        return rslt

    def chk_dir(self):
        os.makedirs(self.log_dir, exist_ok=True)

    def _get_logger(self):
        default_format = "%(asctime)s [%(levelname)s]:%(message)s"
        logging.basicConfig(
            format=default_format, level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S"
        )
        formatter = logging.Formatter(default_format)
        handler = TimedRotatingFileHandler(
            os.path.join(self.log_dir, "call_bicycle_api.log"),
            when="midnight",
            backupCount=7,
        )
        handler.suffix = "%Y-%m-%d"
        handler.setFormatter(formatter)
        logger = logging.getLogger(__name__)
        logger.addHandler(handler)

        return logger


if __name__ == "__main__":
    real_bicycle = RealtimeBicycle(dataset_nm="bikeList")
    items = real_bicycle.call()
    print(items[0:10])
