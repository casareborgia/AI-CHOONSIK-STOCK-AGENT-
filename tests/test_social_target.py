# ==============================================================================
# [AI Trading Agent] 단위 테스트: 소셜 미디어 타겟 수집 검증 (tests/test_social_target.py)
# ==============================================================================

import unittest
import sys
import os

# 프로젝트 루트 디렉토리를 path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.social_scanner import fetch_target_stocktwits_sentiment, fetch_target_reddit_sentiment

from learning.data_quality import Provenance

class TestSocialTargetSentiment(unittest.TestCase):
    def test_stocktwits_aapl(self):
        """StockTwits에서 AAPL의 감성 분석이 정상 동작하는지 테스트합니다."""
        print("\n[Test] StockTwits AAPL Sentiment fetching...")
        res = fetch_target_stocktwits_sentiment("AAPL", limit=10)
        
        self.assertIsInstance(res, Provenance)
        if res.is_usable:
            val = res.value
            self.assertIn("bullish_pct", val)
            self.assertIn("total_count", val)
            self.assertIn("messages", val)
            
            self.assertTrue(0.0 <= val["bullish_pct"] <= 100.0)
            self.assertIsInstance(val["messages"], list)
            
            print(f" -> Success. Bullish %: {val['bullish_pct']}% (Total Feeds: {val['total_count']})")
            if val["messages"]:
                print(f" -> Latest message sample: {val['messages'][0]}")
        else:
            print(f" -> Unavailable/Degraded. Detail: {res.detail}")

    def test_reddit_tsla(self):
        """Reddit에서 TSLA의 검색이 정상 동작하는지 테스트합니다."""
        print("\n[Test] Reddit TSLA Sentiment searching...")
        res = fetch_target_reddit_sentiment("TSLA", subreddits=("stocks", "investing"), limit=3)
        
        self.assertIsInstance(res, Provenance)
        if res.is_usable:
            val = res.value
            print(f" -> Success. Found {len(val)} posts mentioning TSLA.")
            for post in val[:2]:
                self.assertIn("subreddit", post)
                self.assertIn("title", post)
                self.assertIn("score", post)
                print(f"   - [r/{post['subreddit']}] {post['title']} (Score: {post['score']})")
        else:
            print(f" -> Unavailable/Degraded. Detail: {res.detail}")


if __name__ == "__main__":
    unittest.main()
