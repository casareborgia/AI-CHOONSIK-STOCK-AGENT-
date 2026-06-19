import sys
import os
import unittest
import asyncio
from unittest.mock import patch, MagicMock

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from message_bus.broker import MessageBroker
from agents.thesis_agent import ThesisAgent
from agents.critic_agent import CriticAgent
import config


class TestAgentDebate(unittest.IsolatedAsyncioTestCase):
    """
    ThesisAgent와 CriticAgent 간의 1:1 토론 체인(Chat Chain) 비동기 수동 통합 검증
    """
    async def asyncSetUp(self):
        self.broker = MessageBroker()
        self.thesis_agent = ThesisAgent("TestThesisAgent", self.broker)
        self.critic_agent = CriticAgent("TestCriticAgent", self.broker)

        # 텔레그램 알림 발송은 테스트 시 생략하기 위해 Mock 처리
        self.thesis_agent.send_alert = MagicMock(return_value=asyncio.sleep(0))
        self.thesis_agent.bot_token = "mock_token"
        self.thesis_agent.chat_id = "mock_chat_id"

        # 모니터링 태스크는 수동 테스트를 위해 주기적 기동을 막거나 setUp 시 미기동
        self.thesis_agent._periodic_monitor_loop = MagicMock(return_value=asyncio.sleep(0))

    async def asyncTearDown(self):
        await self.thesis_agent.stop()
        await self.critic_agent.stop()

    @patch("core.thesis_evaluator.call_ollama")
    @patch("core.toss_client.TossClient.get_candles")
    @patch("core.technical_engine.evaluate_signal")
    async def test_debate_flow_ends_successfully(self, mock_eval_signal, mock_get_candles, mock_call_ollama):
        """Turn 1 요청 -> Critic 비판(Turn 2) -> Thesis 최종 합의(Reconciliation)로 이어지는 메시지 시퀀스 검증"""
        
        # 1. Mock 설정
        mock_get_candles.return_value = MagicMock() # 더미 DataFrame
        mock_eval_signal.return_value = {
            "regime": "reversed",
            "signal": "⚠️ 투매폭발 (리스크주의)",
            "vol_ratio": 2.5,
            "stoch_summary": "S:▼ M:▲ L:▼"
        }
        
        # call_ollama가 번갈아 가며 Critic 비판서와 Thesis 합의서를 반환하게 세팅
        mock_call_ollama.side_effect = [
            "위험 지표 감지! 주가가 단기적으로 역배열이며 투매가 발생하고 있어 매수 시 손실 우려가 큽니다.", # CRO 비판서
            "[FINAL DEBATE RECONCILIATION] 호재 뉴스에도 불구하고 기술적으로 역배열 및 투매폭발 신호가 발생하여 비중을 축소하고 관망할 것을 권장합니다." # 최종 합의서
        ]

        # 2. 에이전트 구동
        await self.thesis_agent.start()
        await self.critic_agent.start()

        # 3. 가상 1차 데이터 적재 및 Turn 1 디베이트 수동 개시
        payload_data = {
            "ticker": "TSLA",
            "thesis_map": {"ticker": "TSLA", "investment_thesis": "테슬라 전기차 성장성"},
            "news_list": [{"title": "신규 기가팩토리 발표", "publisher": "Reuters", "publish_time": "12:00", "link": "http://test", "uuid": "u1"}],
            "initial_evaluation": "[1차 평가] 전기차 충전망 호재로 단기 상승 모멘텀 확보 (Bullish)",
            "criticism": None,
            "final_reconciliation": None
        }

        # Shared Memory에 올리기
        payload_tag = await self.broker.put_payload("debate:TSLA", payload_data)

        # 4. 강제로 turn 1 메시지 발행
        debate_msg = {
            "ticker": "TSLA",
            "payload_tag": payload_tag,
            "turn": 1
        }
        
        await self.broker.publish("thesis/debate_request", debate_msg)

        # 5. 비동기 큐 처리 시간 대기 (토론 2단계 메시지 왕복 처리용 시간 제공)
        await asyncio.sleep(1.0)

        # 6. 최종 합의 결과 확인
        final_payload = await self.broker.get_payload(payload_tag)
        self.assertIsNotNone(final_payload)
        
        # Critic의 비판문 작성 확인
        self.assertIsNotNone(final_payload["criticism"])
        self.assertIn("위험 지표 감지!", final_payload["criticism"])
        
        # Thesis의 최종 성찰합의문 작성 확인
        self.assertIsNotNone(final_payload["final_reconciliation"])
        self.assertIn("[FINAL DEBATE RECONCILIATION]", final_payload["final_reconciliation"])
        
        # 텔레그램 발송 함수가 호출되었는지 최종 검증
        self.thesis_agent.send_alert.assert_called_once()
        print("✅ 에이전트 1:1 토론 비동기 체인 테스트 성공!")


if __name__ == "__main__":
    unittest.main()
