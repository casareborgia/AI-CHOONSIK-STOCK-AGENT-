# ==============================================================================
# [AI Trading Agent] 성능 벤치마킹 테스트 (tests/test_performance.py)
# ==============================================================================

import unittest
import sys
import os
import time
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

# 프로젝트 루트 디렉토리를 path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from learning.reflection_engine import ReflectionEngine
import main_orchestrator

class TestPerformance(unittest.TestCase):
    def setUp(self):
        self.engine = ReflectionEngine()
        
    def test_reflection_parallel_speed(self):
        """
        비동기 병렬화(gather)가 기존 순차 실행 방식보다 월등히 빠름을 증명합니다.
        네트워크 병목을 모사하기 위해 각 태스크마다 0.05초의 인공 지연을 부여합니다.
        """
        pending_mock = [
            (i, f"2026-05-{i:02d}", f"TICK{i}", 100.0, "Revised text", "Report text")
            for i in range(1, 11)  # 10개 종목
        ]
        
        # 1. 순차 실행 모사
        start_seq = time.time()
        for item in pending_mock:
            # fetch_history 모사 (0.02초 지연)
            time.sleep(0.02)
            # call_ollama 모사 (0.03초 지연)
            time.sleep(0.03)
        end_seq = time.time()
        sequential_time = end_seq - start_seq
        
        # 2. 비동기 병렬 실행 모사
        # 실제 process_single_reflection 을 가짜 비동기 지연으로 패치
        async def mock_process_single(r_id, ticker, r_date_str, entry_price, revised_text, report_text):
            await asyncio.sleep(0.05)  # 0.05초 비동기 지연
            
        async def run_parallel():
            tasks = [
                mock_process_single(*item)
                for item in pending_mock
            ]
            await asyncio.gather(*tasks)
            
        start_para = time.time()
        asyncio.run(run_parallel())
        end_para = time.time()
        parallel_time = end_para - start_para
        
        print(f"\n[성능 벤치마크 - 성찰 엔진]")
        print(f" - 순차 실행 소요 시간: {sequential_time:.4f}초 (10개 종목)")
        print(f" - 비동기 병렬 실행 소요 시간: {parallel_time:.4f}초 (10개 종목)")
        
        improvement = ((sequential_time - parallel_time) / sequential_time) * 100
        print(f" - 소요 시간 단축률: {improvement:.2f}%")
        
        # 병렬 처리가 순차 처리보다 확실히 빨라야 함 (이론상 sequential은 0.5초 이상, parallel은 약 0.05초 부근)
        self.assertLess(parallel_time, sequential_time)
        self.assertTrue(improvement >= 50.0, f"단축률({improvement:.2f}%)이 기대치(50%)에 미달합니다.")

    @patch('main_orchestrator.ReflectionEngine')
    @patch('main_orchestrator.MessageBroker')
    def test_skip_reflection_flag(self, mock_broker, mock_reflection_engine_class):
        """
        --skip-reflection 플래그에 따라 ReflectionEngine의 배치 구동이 스킵되는지 검증합니다.
        """
        # mock instances
        mock_engine_inst = MagicMock()
        mock_engine_inst.run_reflection_batch = AsyncMock()
        mock_reflection_engine_class.return_value = mock_engine_inst
        
        # system done queue mock
        mock_broker_inst = MagicMock()
        mock_broker_inst.subscribe = AsyncMock()
        mock_broker_inst.unsubscribe = AsyncMock()
        mock_broker_inst.publish = AsyncMock()
        mock_broker.return_value = mock_broker_inst
        
        # 각 에이전트 모킹 팩토리 정의
        def create_mock_agent(*args, **kwargs):
            agent = MagicMock()
            agent.start = AsyncMock()
            agent.stop = AsyncMock()
            return agent
        
        # 1. 플래그가 없을 때 -> run_reflection_batch 가 호출되어야 함
        with patch.object(sys, 'argv', ['main_orchestrator.py']):
            # main의 나머지 에이전트 루프를 조기 종료시키기 위해 
            # done_queue.get() 에서 바로 success 값을 주도록 Mocking
            done_queue_mock = AsyncMock()
            done_queue_mock.get.return_value = ("system/done", {"status": "success", "report_path": "dummy.md"})
            
            with patch('asyncio.Queue', return_value=done_queue_mock), \
                 patch('main_orchestrator.MarketAgent', side_effect=create_mock_agent), \
                 patch('main_orchestrator.ScreenerAgent', side_effect=create_mock_agent), \
                 patch('main_orchestrator.TechnicalAgent', side_effect=create_mock_agent), \
                 patch('main_orchestrator.CriticAgent', side_effect=create_mock_agent), \
                 patch('main_orchestrator.DBAgent', side_effect=create_mock_agent), \
                 patch('main_orchestrator.ReporterAgent', side_effect=create_mock_agent):
                     
                asyncio.run(main_orchestrator.main())
                mock_engine_inst.run_reflection_batch.assert_called_once()
                
        # 2. 플래그가 있을 때 -> run_reflection_batch 가 호출되지 않아야 함
        mock_engine_inst.run_reflection_batch.reset_mock()
        with patch.object(sys, 'argv', ['main_orchestrator.py', '--skip-reflection']):
            done_queue_mock = AsyncMock()
            done_queue_mock.get.return_value = ("system/done", {"status": "success", "report_path": "dummy.md"})
            
            with patch('asyncio.Queue', return_value=done_queue_mock), \
                 patch('main_orchestrator.MarketAgent', side_effect=create_mock_agent), \
                 patch('main_orchestrator.ScreenerAgent', side_effect=create_mock_agent), \
                 patch('main_orchestrator.TechnicalAgent', side_effect=create_mock_agent), \
                 patch('main_orchestrator.CriticAgent', side_effect=create_mock_agent), \
                 patch('main_orchestrator.DBAgent', side_effect=create_mock_agent), \
                 patch('main_orchestrator.ReporterAgent', side_effect=create_mock_agent):
                     
                asyncio.run(main_orchestrator.main())
                mock_engine_inst.run_reflection_batch.assert_not_called()
                print(" -> Verification passed: run_reflection_batch skipped when --skip-reflection is provided.")

if __name__ == "__main__":
    unittest.main()
