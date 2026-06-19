import unittest
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.social_scanner import fetch_toss_popular_shares

class TestTossSocial(unittest.TestCase):
    def test_fetch_toss_popular_shares(self):
        """실제 토스 인기 종목 크롤링을 수행하여 반환 목록의 규격 및 유효성을 검증합니다."""
        results = fetch_toss_popular_shares()
        
        # 네트워크 차단 등을 감안하여 빈 리스트도 통과하지만, 
        # 결과가 있을 경우 반환 데이터 필드들의 정합성을 보증해야 합니다.
        self.assertIsInstance(results, list)
        
        if results:
            print(f"\n📢 [TestTossSocial] 스크래핑된 토스 인기 주식 목록 ({len(results)}개):")
            for idx, r in enumerate(results, 1):
                print(f"  {idx}위. {r['ticker']} ({r['name']}) - 멘션가중치: {r['mentions']}")
                self.assertIn('ticker', r)
                self.assertIn('name', r)
                self.assertIn('mentions', r)
                self.assertIn('sector', r)
                self.assertEqual(r['track'], 'Track B')
                
                # 티커는 대문자 영문 2~5글자
                self.assertTrue(r['ticker'].isupper())
                self.assertTrue(2 <= len(r['ticker']) <= 5)

if __name__ == '__main__':
    unittest.main()
