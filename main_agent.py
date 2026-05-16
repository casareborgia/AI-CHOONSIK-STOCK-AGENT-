# ==============================================================================
# [AI Trading Agent] 파이프라인 메인 오케스트레이터 (Main Agent)
# ==============================================================================
# 시스템 전체의 5대 모듈을 유기적으로 연결하며, 기존 직렬 방식에서 벗어나
# 펀더멘털 우량주(Track A)와 SNS 모멘텀 급등주(Track B)를 비동기(asyncio)로
# 병렬 스캔하는 고성능 듀얼 트랙 오케스트레이터입니다.

import sys
import os
import time
import asyncio

# 현재 디렉토리를 모듈 경로로 등록
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.sector_monitor import get_leading_sectors
from core.fundamental_filter import get_fundamental_candidates
from core.technical_engine import analyze_technical_signals
from core.ai_verify import run_ai_verification
from plugins.social_scanner import get_social_candidates
import reporter


async def execute_track_a(leading_names):
    """
    [Track A] 주도 섹터 기반 펀더멘털 우량주 스윙 트랙 (기존 프로세스 이식)
    동기적 I/O 바운드 함수를 이벤트 루프 차단 없이 스레드 풀에서 병렬 실행합니다.
    """
    print("\n🌲 [Track A 가동] 펀더멘털 우량주 파이프라인 스레드 할당...")
    # asyncio.to_thread를 통해 기존 블로킹 코드를 완벽히 비동기 래핑
    cands = await asyncio.to_thread(get_fundamental_candidates, target_sectors=leading_names)
    
    # 트랙 출처 명시
    for c in cands:
        c['track'] = 'Track A'
        
    return cands


async def execute_track_b():
    """
    [Track B] 재무 무시 커뮤니티 모멘텀 기반 급등주 트랙 (신규 파이프라인)
    """
    print("\n🚀 [Track B 가동] SNS 모멘텀 급등주 비동기 스캐너 할당...")
    cands = await get_social_candidates()
    return cands


async def run_quant_agent_async():
    """
    비동기 기반 탑다운 듀얼 트랙 분석 파이프라인을 관장합니다.
    """
    start_time = time.time()
    print("================================================================================")
    print("🚀 [AI 춘식 MK1] 듀얼 트랙(Dual-Track) 병렬 퀀트 시스템 가동 시작")
    print("================================================================================")
    
    try:
        # [단계 1: 숲 분석] 공통 선행 작업 - 시장 주도 섹터 파악
        leading_names, leading_tickers = get_leading_sectors()
        
        # [단계 2: 병렬 나무 분석] Track A(재무 우량주)와 Track B(SNS 급등주) 동시 스캔
        print("\n⚡ [병렬 연산 가동] Track A & Track B 동시 데이터 수집 시작...")
        results = await asyncio.gather(
            execute_track_a(leading_names),
            execute_track_b()
        )
        
        track_a_candidates, track_b_candidates = results
        
        # 합집합(Union) 병합
        union_candidates = track_a_candidates + track_b_candidates
        
        if not union_candidates:
            print("\n⚠️ 양쪽 트랙 모두에서 조건에 부합하는 종목이 포착되지 않았습니다. 파이프라인을 종료합니다.")
            return
            
        print(f"\n🔗 [병합 완료] 총 {len(union_candidates)}개 후보군 확보 (Track A: {len(track_a_candidates)}개 / Track B: {len(track_b_candidates)}개)")
        
        # [단계 3: 타점 분석] 3중 파동에너지 및 거래량 급증 분석 (트랙별 기준 자동 분기 적용)
        signals = analyze_technical_signals(union_candidates)
        
        # [단계 4: AI 검증] 타점 포착 종목 대상 Gemma 4 맞춤형 프롬프트 검증
        ai_verified_results = run_ai_verification(signals, leading_sectors=leading_names)
        
        # [단계 5: 리포팅] 최종 통합 마크다운 문서 생성 및 텔레그램 발송
        report_path = reporter.generate_markdown_report(leading_names, ai_verified_results)
        tele_msg = reporter.format_telegram_message(leading_names, ai_verified_results)
        
        # [단계 6: 텔레그램 실시간 알림]
        print("\n📱 [텔레그램 전송] 분석 결과를 전송 중입니다...")
        await reporter.send_telegram_message(tele_msg)
        
        # 소요 시간 연산
        elapsed = time.time() - start_time
        print("\n================================================================================")
        print(f"✨ [실행 완료] 병렬 파이프라인 가동 성공 (총 소요시간: {elapsed:.1f}초)")
        print(f"📂 저장된 종합 리포트 경로: {report_path}")
        print("================================================================================")
        
    except Exception as e:
        print(f"\n❌ 파이프라인 비동기 실행 중 치명적 오류 발생: {e}")
        import traceback
        traceback.print_exc()


def run_quant_agent():
    """외부 호출용 동기 엔트리 포인트 래퍼"""
    asyncio.run(run_quant_agent_async())


if __name__ == "__main__":
    run_quant_agent()
