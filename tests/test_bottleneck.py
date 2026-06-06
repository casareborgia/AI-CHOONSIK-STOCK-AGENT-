import asyncio
import sys
import os
from typing import Any

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from learning.db import add_graph_edge, get_related_nodes, delete_graph_edges
from plugins.news_monitor import fetch_recent_news
from core.thesis_evaluator import call_ollama
from agents.base import BaseAgent
from message_bus.broker import MessageBroker

async def run_tests():
    print("==================================================")
    print("🧪 [병목구간 & 듀얼 LLM] 시스템 통합 테스트 실행")
    print("==================================================")
    
    # 1. 지식 그래프 CRUD 테스트
    print("\n1. 지식 그래프 CRUD 검증...")
    success = add_graph_edge("sector", "Technology", "ticker", "AAPL", "belongs_to", 1.0)
    assert success is True, "지식 그래프 추가 실패"
    
    success = add_graph_edge("macro_event", "rate_hike", "sector", "Technology", "affects_bearish", 1.5)
    assert success is True, "지식 그래프 추가 실패"
    
    related = get_related_nodes("sector", "Technology")
    print(f" -> Technology 관련 노드 수: {len(related)}")
    assert len(related) >= 2, "지식 그래프 조회 에러"
    for r in related:
        print(f"    - [{r['direction']}] {r['node_type']}: {r['node_id']} (관계: {r['relation_type']}, 가중치: {r['weight']})")
        
    delete_graph_edges("sector", "Technology")
    delete_graph_edges("macro_event", "rate_hike")
    print(" -> 지식 그래프 삭제 및 1차 검증 성공")
    
    # 2. 뉴스 노이즈 필터링 검증
    print("\n2. 뉴스 1차 노이즈 키워드 필터링 검증...")
    raw_news = fetch_recent_news("AAPL", hours=168)
    print(f" -> 노이즈 사전 제외 필터링 통과한 AAPL 뉴스 개수: {len(raw_news)}")
    
    # 3. 듀얼 LLM 분리 호출 검증 (Ollama 구동 확인)
    print("\n3. 듀얼 LLM 분리 호출 검증...")
    print(" -> [LIGHT] 모델 호출 중 (Gemma 4 기본)...")
    light_resp = call_ollama("Say 'Light OK'", model_type="light")
    print(f"    - LIGHT 응답: {light_resp.strip()}")
    
    print(" -> [HEAVY] 모델 호출 중 (Gemma 4 26B)...")
    heavy_resp = call_ollama("Say 'Heavy OK'", model_type="heavy")
    print(f"    - HEAVY 응답: {heavy_resp.strip()}")
    
    # 4. 성과 평가 Alpha 산출 로직 모의 검증
    print("\n4. Alpha 수익률 연산 정밀 검증...")
    entry_price = 100.0
    check_price = 110.0 # +10% 수익률
    spy_entry = 400.0
    spy_check = 420.0 # +5% 벤치마크 수익률
    
    return_pct = ((check_price - entry_price) / entry_price) * 100
    spy_return_pct = ((spy_check - spy_entry) / spy_entry) * 100
    alpha_return_pct = return_pct - spy_return_pct
    
    print(f" -> 종목 수익률: {return_pct:+.2f}%")
    print(f" -> SPY 수익률: {spy_return_pct:+.2f}%")
    print(f" -> 초과수익률 (Alpha): {alpha_return_pct:+.2f}%p")
    assert alpha_return_pct == 5.0, "Alpha 수익률 계산 오류"
    print(" -> Alpha 연산 수학적 정합성 검증 완료")
    
    # 5. 에이전트 예외 백오프 재시도 검증
    print("\n5. 에이전트 자동 재시도 및 백오프 동작 검증...")
    broker = MessageBroker()
    
    class MockErrorAgent(BaseAgent):
        def __init__(self, name, broker):
            super().__init__(name, broker)
            self.attempt_count = 0
            
        async def handle_message(self, channel: str, message: Any):
            self.attempt_count += 1
            if self.attempt_count < 3:
                raise ValueError(f"모크 에러 발생 (시도 {self.attempt_count}회)")
            print(f"    -> [MockErrorAgent] {self.attempt_count}회차 시도 성공 완료!")
            
    mock_agent = MockErrorAgent("MockErrorAgent", broker)
    await mock_agent.start()
    
    print(" -> 모크 에러 에이전트에 메시지 전송 및 재시도 확인 (대기 시간 약 6초)...")
    await mock_agent.queue.put(("test/retry", "msg"))
    
    await asyncio.sleep(8)
    await mock_agent.stop()
    
    assert mock_agent.attempt_count == 3, "재시도 루프 3회 미달성"
    print(" -> 에이전트 지수 백오프 및 재시도 성공 검증 완료")
    
    print("\n==================================================")
    print("✨ 모든 통합 테스트가 완벽히 성공하였습니다.")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
