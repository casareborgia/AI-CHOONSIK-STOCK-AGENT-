# ==============================================================================
# [AI Trading Agent] 단위 테스트: 소셜 미디어 타겟 수집 검증 (tests/test_social_target.py)
# ==============================================================================

import unittest
import sys
import os

# 프로젝트 루트 디렉토리를 path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.social_scanner import fetch_target_stocktwits_sentiment, fetch_target_reddit_sentiment

class TestSocialTargetSentiment(unittest.TestCase):
    def test_stocktwits_aapl(self):
        """StockTwits에서 AAPL의 감성 분석이 정상 동작하는지 테스트합니다."""
        print("\n[Test] StockTwits AAPL Sentiment fetching...")
        res = fetch_target_stocktwits_sentiment("AAPL", limit=10)
        
        self.assertIsInstance(res, dict)
        self.assertIn("bullish_pct", res)
        self.assertIn("total_count", res)
        self.assertIn("messages", res)
        
        self.assertTrue(0.0 <= res["bullish_pct"] <= 100.0)
        self.assertIsInstance(res["messages"], list)
        
        print(f" -> Success. Bullish %: {res['bullish_pct']}% (Total Feeds: {res['total_count']})")
        if res["messages"]:
            print(f" -> Latest message sample: {res['messages'][0]}")

    def test_reddit_tsla(self):
        """Reddit에서 TSLA의 검색이 정상 동작하는지 테스트합니다."""
        print("\n[Test] Reddit TSLA Sentiment searching...")
        res = fetch_target_reddit_sentiment("TSLA", subreddits=("stocks", "investing"), limit=3)
        
        self.assertIsInstance(res, list)
        print(f" -> Success. Found {len(res)} posts mentioning TSLA.")
        for post in res[:2]:
            self.assertIn("subreddit", post)
            self.assertIn("title", post)
            self.assertIn("score", post)
            print(f"   - [r/{post['subreddit']}] {post['title']} (Score: {post['score']})")


if __name__ == "__main__":
    unittest.main()
