import asyncio
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from learning.db import add_or_update_thesis, get_thesis_map, get_all_thesis_maps, delete_thesis_map
from core.thesis_evaluator import generate_initial_thesis_map, evaluate_thesis_change
from plugins.news_monitor import fetch_recent_news

async def run_tests():
    print("==================================================")
    print("🧪 [테스트 가동] Thesis 감시 및 텔레그램 연동 단위 테스트")
    print("==================================================")
    
    # 1. DB CRUD 테스트
    print("\n1. DB CRUD 테스트 진행 중...")
    test_ticker = "TEST"
    test_data = {
        "investment_thesis": "테스트용 투자 아이디어",
        "key_indicators": "테스트 지표",
        "catalysts": "테스트 촉매",
        "risks": "테스트 리스크",
        "kill_condition": "테스트 킬 조건",
        "noise_rules": "잡뉴스 조건",
        "earnings_checkpoints": "실적 체크",
        "valuation_criteria": "밸류에이션 기준",
        "one_line_conclusion": "한 줄 결론"
    }
    
    # 저장 및 업데이트
    save_success = add_or_update_thesis(test_ticker, "Test Company", test_data)
    assert save_success is True, "DB 저장 실패"
    print(" -> DB 저장/업데이트 성공")
    
    # 단건 조회
    fetched = get_thesis_map(test_ticker)
    assert fetched.get("ticker") == test_ticker, "DB 조회 실패"
    print(f" -> 단건 조회 성공 (회사명: {fetched.get('name')})")
    
    # 전체 조회
    all_maps = get_all_thesis_maps()
    assert len(all_maps) > 0, "전체 조회 결과 빈 값"
    print(f" -> 전체 조회 성공 (등록 개수: {len(all_maps)})")
    
    # 2. 뉴스 수집 테스트 (AAPL)
    print("\n2. yfinance 뉴스 수집 테스트 진행 중...")
    aapl_news = fetch_recent_news("AAPL", hours=48)
    print(f" -> AAPL 최근 48시간 뉴스 수집 완료: {len(aapl_news)}건 수집")
    if aapl_news:
        print(f"    (샘플 뉴스 타이틀: {aapl_news[0]['title']})")
        
    # 3. LLM 분석 테스트 (Gemma 4 호출)
    print("\n3. Ollama/Gemma 4 연동 분석 테스트 진행 중...")
    mock_news = [
        {
            "title": "Test Company announces massive growth in FCF and margins",
            "publisher": "Mock News",
            "publish_time": "2026-06-07 00:00:00",
            "link": "http://mock.link"
        }
    ]
    
    # Thesis 변화 평가
    print(" -> LLM 분석 요청 중 (약 5~15초 소요)...")
    eval_res = evaluate_thesis_change(test_ticker, test_data, mock_news)
    print(f" -> LLM 분석 완료 (변화 발생 여부: {eval_res.get('has_change')})")
    print("--------------------------------------------------")
    print(eval_res.get("evaluation_text"))
    print("--------------------------------------------------")
    
    # 4. DB 삭제 테스트
    print("\n4. DB 삭제 테스트 진행 중...")
    del_success = delete_thesis_map(test_ticker)
    assert del_success is True, "DB 삭제 실패"
    print(" -> DB 삭제 완료 및 CRUD 테스트 정상 통과")
    
    print("\n==================================================")
    print("✨ 모든 단위 테스트가 정상적으로 종료되었습니다.")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
