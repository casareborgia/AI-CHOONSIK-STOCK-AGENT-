# ==============================================================================
# [AI Trading Agent] 코어 공통 모듈: 토스증권 API 클라이언트 (Toss Client)
# ==============================================================================
# 토스증권 Open API를 통해 캔들 데이터(일봉/분봉)를 조회합니다.
# OAuth2 클라이언트 크레덴셜 기반 토큰 갱신 로직을 포함하며, 
# 수집된 데이터를 yfinance의 history() 출력 포맷과 호환되는 pandas DataFrame으로 변환합니다.

import time
import logging
import pandas as pd
import httpx

import config

logger = logging.getLogger("TossClient")


class TossClient:
    """
    토스증권 Open API 통신을 위한 시세 조회 전용 클라이언트 (Read-Only)
    """
    def __init__(self):
        self.base_url = config.TOSS_API_BASE_URL
        self.client_id = config.TOSS_CLIENT_ID
        self.client_secret = config.TOSS_CLIENT_SECRET
        
        self._access_token = None
        self._expires_at = 0.0

    def _is_token_expired(self) -> bool:
        """토큰이 만료되었거나 만료 임박(60초 전) 상태인지 검사"""
        if not self._access_token:
            return True
        # 현재 시간에 60초 버퍼 추가
        return time.time() + 60.0 >= self._expires_at

    def _fetch_access_token(self):
        """OAuth2 Client Credentials 방식으로 신규 액세스 토큰 획득"""
        if not self.client_id or not self.client_secret:
            raise ValueError("토스증권 API 연결을 위한 TOSS_CLIENT_ID 또는 TOSS_CLIENT_SECRET 설정이 누락되었습니다. .env를 확인하세요.")

        url = f"{self.base_url}/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            logger.info("🔑 토스증권 OAuth2 토큰 발급 시도 중...")
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, data=payload, headers=headers)
                
                if response.status_code != 200:
                    logger.error(f"❌ 토큰 발급 실패 (HTTP {response.status_code}): {response.text}")
                    response.raise_for_status()

                res_data = response.json()
                self._access_token = res_data["access_token"]
                
                # expires_in초 후 만료 (만료 시각 계산)
                expires_in = float(res_data.get("expires_in", 86400))
                self._expires_at = time.time() + expires_in
                
                logger.info(f"✅ 토스증권 API 액세스 토큰이 성공적으로 갱신되었습니다. (유효시간: {expires_in:.0f}초)")

        except Exception as e:
            logger.error(f"❌ 토스증권 토큰 발급 중 예외 발생: {e}")
            raise

    def get_headers(self) -> dict:
        """API 호출에 필요한 공용 인증 헤더 획득 (유효 토큰 보장)"""
        if self._is_token_expired():
            self._fetch_access_token()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json"
        }

    def get_candles(self, symbol: str, interval: str = "1d", count: int = 120) -> pd.DataFrame:
        """
        특정 종목의 캔들 데이터를 조회하고 yfinance 호환 DataFrame으로 변환합니다.
        
        :param symbol: 종목 코드 (예: 삼성전자 '005930', 애플 'AAPL')
        :param interval: 봉 단위 ('1m' 또는 '1d')
        :param count: 조회할 봉 수 (최대 200)
        :return: yfinance 포맷 DataFrame (인덱스: Date, 열: Open, High, Low, Close, Volume)
        """
        # 토스 API는 대문자 심볼을 권장하며, 국내 6자리 코드 및 해외 영문 티커 매칭
        symbol = str(symbol).strip().upper()
        url = f"{self.base_url}/api/v1/candles"
        params = {
            "symbol": symbol,
            "interval": interval,
            "count": min(count, 200)
        }

        try:
            headers = self.get_headers()
            with httpx.Client(timeout=15.0) as client:
                response = client.get(url, params=params, headers=headers)
                
                if response.status_code == 404:
                    raise FileNotFoundError(f"존재하지 않는 종목이거나 시세를 찾을 수 없습니다: {symbol}")
                elif response.status_code != 200:
                    logger.error(f"❌ 토스 캔들 API 호출 실패 (HTTP {response.status_code}): {response.text}")
                    response.raise_for_status()

                res_data = response.json()
                
                # response envelope에서 result 추출
                result = res_data.get("result", {})
                candles_list = result.get("candles", [])
                
                if not candles_list:
                    raise ValueError(f"토스 캔들 API 결과가 비어있습니다: {symbol}")

                # DataFrame 생성
                df = pd.DataFrame(candles_list)

                # 컬럼 매핑 및 전처리
                # 토스 API 스펙 컬럼: timestamp, openPrice, highPrice, lowPrice, closePrice, volume, currency
                # yfinance 스펙 컬럼: Date(Index), Open, High, Low, Close, Volume
                df['Date'] = pd.to_datetime(df['timestamp'])
                df.set_index('Date', inplace=True)

                # 데이터 타입 변환 및 명칭 변경
                rename_map = {
                    'openPrice': 'Open',
                    'highPrice': 'High',
                    'lowPrice': 'Low',
                    'closePrice': 'Close',
                    'volume': 'Volume'
                }
                df.rename(columns=rename_map, inplace=True)
                
                # 필요한 컬럼만 추출 및 타입 캐스팅
                keep_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
                df = df[keep_cols].copy()
                
                df['Open'] = df['Open'].astype(float)
                df['High'] = df['High'].astype(float)
                df['Low'] = df['Low'].astype(float)
                df['Close'] = df['Close'].astype(float)
                df['Volume'] = df['Volume'].astype(float) # yfinance는 Volume을 float으로 처리함

                # 토스 API는 최신 데이터가 인덱스 0번에 위치하므로(내림차순),
                # 파동 계산을 위해 날짜 기준 오름차순(과거 -> 최신)으로 재정렬합니다.
                df.sort_index(inplace=True)

                return df

        except Exception as e:
            logger.error(f"❌ [TossClient] {symbol} 시세 수집 중 오류: {e}")
            raise


# 싱글톤 인스턴스 노출
toss_client = TossClient()
