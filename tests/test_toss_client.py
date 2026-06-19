import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.toss_client import TossClient
import config


class TestTossClient(unittest.TestCase):
    """
    TossClient 클래스의 개별 단위 기능 검증 테스트
    """
    def setUp(self):
        # 테스트 전용 TossClient 인스턴스 생성
        self.client = TossClient()
        self.client.client_id = "test_client_id"
        self.client.client_secret = "test_client_secret"

    @patch("httpx.Client.post")
    def test_fetch_access_token_success(self, mock_post):
        """액세스 토큰이 정상적으로 발급 및 캐싱되는지 테스트"""
        # 모의 응답 정의
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "mocked_jwt_token_12345",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        mock_post.return_value = mock_response

        # 실행
        self.client._fetch_access_token()

        # 검증
        self.assertEqual(self.client._access_token, "mocked_jwt_token_12345")
        self.assertGreater(self.client._expires_at, 0)
        self.assertFalse(self.client._is_token_expired())

    @patch("httpx.Client.get")
    @patch("core.toss_client.TossClient.get_headers")
    def test_get_candles_format_conversion(self, mock_get_headers, mock_get):
        """토스 API 응답 데이터가 yfinance 호환 포맷으로 오름차순 정렬 및 타입 캐스팅되는지 검증"""
        # 모의 인증 헤더 지정
        mock_get_headers.return_value = {"Authorization": "Bearer mocked"}

        # 모의 캔들 조회 API 응답 정의 (최신 데이터가 앞쪽에 있는 내림차순 배열)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "candles": [
                    {
                        "timestamp": "2026-03-25T09:00:00+09:00",
                        "openPrice": "72000",
                        "highPrice": "72500",
                        "lowPrice": "71800",
                        "closePrice": "72100",
                        "volume": "1000",
                        "currency": "KRW"
                    },
                    {
                        "timestamp": "2026-03-24T09:00:00+09:00",
                        "openPrice": "71500",
                        "highPrice": "71900",
                        "lowPrice": "71100",
                        "closePrice": "71600",
                        "volume": "1500",
                        "currency": "KRW"
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        # 실행
        df = self.client.get_candles("005930", interval="1d", count=2)

        # 검증
        self.assertIsInstance(df, pd.DataFrame)
        
        # 1. 컬럼명 변환 확인 (yfinance 호환)
        self.assertListEqual(list(df.columns), ['Open', 'High', 'Low', 'Close', 'Volume'])
        
        # 2. 인덱스가 DatetimeIndex이며 정렬 여부 검증 (과거가 먼저 오도록 오름차순 정렬 확인)
        self.assertEqual(df.index[0], pd.to_datetime("2026-03-24T09:00:00+09:00"))
        self.assertEqual(df.index[1], pd.to_datetime("2026-03-25T09:00:00+09:00"))
        
        # 3. 데이터 타입 검증 (float 확인)
        self.assertEqual(df['Close'].dtype, float)
        self.assertEqual(df['Volume'].dtype, float)
        self.assertEqual(df.loc[df.index[1], 'Close'], 72100.0)

    @unittest.skipIf(not os.getenv("TOSS_CLIENT_ID"), "토스증권 실전 API 키가 환경변수에 제공되지 않아 통과")
    def test_real_toss_api_integration(self):
        """실제 환경변수에 API Key가 제공된 경우 실전 연결 및 시세 작동 여부 검증"""
        real_client = TossClient()
        try:
            # 실제 주가 수집 시도 (테스트용으로 AAPL 일봉 5개 호출)
            df = real_client.get_candles("AAPL", interval="1d", count=5)
            self.assertGreater(len(df), 0)
            print(f"\n[Real Integration Pass] AAPL 일봉: \n{df}")
        except Exception as e:
            self.fail(f"실제 토스 API 호출 실패: {e}")


if __name__ == "__main__":
    unittest.main()
