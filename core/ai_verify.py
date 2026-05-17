# ==============================================================================
# [AI Trading Agent] 코어 모듈 4: 심층검증기 (AI Verify)
# ==============================================================================
# 로컬 Ollama(Gemma 4) API를 호출하여 최종 선별된 종목들의 재무 및 파동 상태를
# 종합 분석하고, 상승 촉매제(Catalyst)와 구체적 매매 전략 내러티브를 생성합니다.
# 
# [정합성 극대화] 과거 날짜가 찍히는 할루시네이션(Hallucination)을 완벽 차단하기 위해
# 프롬프트 상단에 당일 기준일자를 강제 주입하며, Track B(밈 트랙) 종목일지라도 
# 회사의 실제 섹터 및 고유 가치 기반으로 입체적 분석을 유도합니다.

import sys
import os
import json
import urllib.request
from datetime import datetime

# 부모 디렉토리 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config


def call_ollama(prompt):
    """
    로컬 Ollama 서버와 통신하여 스트림이 아닌 전체 텍스트 응답을 반환합니다.
    """
    url = config.OLLAMA_ENDPOINT
    payload = {
        "model": config.TARGET_LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,  # 날짜 등 팩트 정확성을 극대화하기 위해 온도 최소화
            "top_p": 0.95
        }
    }
    
    try:
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=180) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            return res_data.get("response", "응답 생성 실패")
            
    except Exception as e:
        return f"⚠️ 로컬 AI 통신 실패 (Ollama 서버 확인 필요): {e}"


def generate_ai_narrative(candidate, leading_sectors=None):
    """
    개별 종목 데이터를 기반으로 분석 프롬프트를 작성하고 AI 브리핑을 생성합니다.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    ticker = candidate.get('ticker', 'UNKNOWN')
    name = candidate.get('name', ticker)
    signal = candidate.get('signal', '관망')
    inst_own = candidate.get('inst_own', 0.0)
    fcf = candidate.get('fcf', 0)
    vol_ratio = candidate.get('vol_ratio', 1.0)
    sector = candidate.get('disp_sector', candidate.get('sector', 'Unknown'))
    close = candidate.get('close', 0.0)
    
    pe = candidate.get('pe', 0.0)
    peg = candidate.get('peg', 0.0)
    ev_ebitda = candidate.get('ev_ebitda', 0.0)
    high_52w = candidate.get('high_52w', 0.0)
    
    # 52주 고점 대비 위치 연산
    pos_52w_str = "위치 정보 없음"
    if high_52w > 0:
        dist = ((high_52w - close) / high_52w) * 100
        pos_52w_str = f"52주 최고가(${high_52w:.2f}) 대비 -{dist:.1f}% 근접"
        
    track = candidate.get('track', 'Track A')
    mentions = candidate.get('mentions', 0)
    
    # 변동성(Beta) 지표 추출 및 동적 손절선 계산
    beta = candidate.get('beta', 1.0)
    if beta is None or beta <= 0:
        beta = 1.0
    stop_loss_pct = round(max(5.0, min(12.0, 5.0 * beta)))
    
    # 공통 프롬프트 헤더 (클로드 지적사항 완벽 반영 지침)
    base_guideline = f"""[절대 준수 지침]
- 본 보고서의 작성 일자(Date)는 반드시 현재 기준일인 **{today_str}**로 명시하십시오. 과거 연도 출력을 원천 금지합니다.
- 'Confidential / Institutional Use Only' 등 실체 이상의 과도한 권위를 부여하는 장식성 문구 사용을 절대 금지합니다.
- **[거래량 및 위치의 리스크]**: 저거래량(20일 평균 대비 1.2배 미만)을 무조건적인 '에너지 응축/매집 기회'로만 편향되게 서술하지 말고, 52주 고점 부근 등 위치에 따라 '상방 에너지 소진 및 유동성 고갈 위험성'의 이면도 함께 서술하여 객관적 균형감을 유지하십시오.
- **[이익의 질(Earnings Quality) 검증]**: 에너지/원자재 등 전통 섹터의 P/E가 25배 이상으로 이례적으로 높게 집계된 경우, 단순히 PEG가 1.0 미만이라는 이유만으로 "저평가"라 단정하지 마십시오. 이는 원자재 가격 하락 등으로 E(이익)가 일시적으로 심하게 눌려(Compressed) 밸류에이션이 왜곡되었을 가능성(기저효과 리스크)이 매우 높습니다. 반드시 이익의 질적 변동성 및 동종 업계 평균(P/E 10~15배) 대비 과열 리스크를 구체적으로 지적하십시오.
- **[기관 지분율 > 100% 공매도 착시]**: 기관 지분율이 100%를 초과하는 현상(예: {inst_own:.1f}%)은 단순한 수급 호재가 아닌, '대규모 공매도(Short Interest) 잔고로 인한 주가 이중 대차 집계'의 착시임을 지적해야 합니다. 숏스퀴즈 발생 가능성과 숏포지션의 강력한 하방 압력 리스크 양면을 균형 있게 논평하십시오.
- **[시그널-펀더멘털 괴리 해석]**: 기술적 시그널({signal})이 강하더라도 펀더멘털 지표(P/E: {pe:.2f}, PEG: {peg:.2f})상으로 심각한 버블이나 적자 부담이 존재한다면, 맹목적인 매수 추천 대신 "기술적 추세와 펀더멘털적 리스크 간의 괴리"를 냉철하게 경고하고 관망 또는 철저한 비중 조절을 권고하십시오.
- **[변동성(Beta) 반영 동적 손절선]**: 본 종목의 체계적 위험(Beta)은 **{beta:.2f}**입니다. 손절 기준은 종목 고유의 변동성을 반영하여 이평선과 혼용하지 말고, 오직 **진입가 대비 -{stop_loss_pct}% 도달 시 즉각 매도**하는 단일 기계적 리스크 차단 수칙으로 통일하십시오. (Low-Beta는 5%, High-Beta는 최대 12%까지 동적 적용됨)
"""

    if track == 'Track B':
        prompt = f"""{base_guideline}
당신은 월스트리트의 입체적 퀀트 애널리스트이자 리스크 매니저입니다.
아래 종목은 커뮤니티 언급량 폭증으로 포착된 모멘텀 트랙(Track B) 종목이지만, 실제 고유 섹터와 펀더멘털을 겸비하고 있습니다.

[분석 대상 종목 데이터]
- 티커: {ticker} ({name})
- 표기 소속 섹터: {sector}
- 포착 트랙: SNS 모멘텀 (Track B)
- 최근 언급량: 최소 {mentions}회 이상 폭증 추세
- 기술적 타점: {signal} (파동 요약: {candidate.get('stoch_summary', '')})
- 거래량 상태: 20일 평균 대비 {vol_ratio:.2f}배
- 밸류에이션 지표: P/E {pe:.2f}, PEG {peg:.2f}, EV/EBITDA {ev_ebitda:.2f} ({pos_52w_str})

[작성 요구사항]
1. **투자 핵심 요약**: 회사의 실제 사업 분야({sector})와 모멘텀 수급이 결합된 기술적 위치를 밸류에이션 부담 여부와 함께 2문장으로 압축.
2. **모멘텀 재료의 본질 파악 (Catalyst 진위)**: 무조건적인 밈(Meme) 주식으로 단정 짓지 말고, 실제 회사의 최근 실적이나 고유 호재가 커뮤니티 수급을 촉발했는지 균형 잡힌 시각으로 분석.
3. **고변동성 및 밸류에이션 리스크 경고**: 가치 대비 프리미엄 여부 지적 및 수급 쏠림에 따른 변동성/유동성 고갈 위험성 고지.
4. **실전 트레이딩 전략**: 가용 자산의 5~10% 내외 비중 제시, 타이트한 분할 익절가와 함께 **진입가 대비 -{stop_loss_pct}% 도달 시 즉각 전량 매도**하는 단일화된 손절 수칙을 강력히 제시.

한국어로 전문적인 퀀트 리포트 양식에 맞춰 출력하십시오.
"""
    elif track == 'Track C':
        prompt = f"""{base_guideline}
당신은 글로벌 최상위 헤지펀드의 보수적인 퀀트 리스크 매니저입니다.
아래 종목은 13F 스마트 머니(Track C)가 집중 매집한 우량주입니다.

[분석 대상 종목 데이터]
- 티커: {ticker} ({name})
- 표기 소속 섹터: {sector}
- 재무 건전성: 기관 지분율 {inst_own:.1f}%, 잉여현금흐름(FCF) ${fcf:,.0f}
- 밸류에이션 지표: P/E {pe:.2f}, PEG {peg:.2f}, EV/EBITDA {ev_ebitda:.2f} ({pos_52w_str})
- 기술적 타점: {signal} (파동 요약: {candidate.get('stoch_summary', '')})
- 거래량 상태: 20일 평균 대비 {vol_ratio:.2f}배

[작성 요구사항]
1. 기관 수급의 지속성과 해당 기업의 FCF(잉여현금흐름) 방어력을 중심으로 안정성을 평가하십시오.
2. 밸류에이션(P/E, PEG)이 역사적 밴드 내에서 안전 마진(Margin of Safety)을 확보하고 있는지 엄격히 검증하십시오.
3. 실전 매매 전략: 포트폴리오의 **핵심 자산(Core Asset)**으로서 총 투자금의 **10%~20% 비중** 분할 매수를 제안하고, **진입가 대비 -{stop_loss_pct}% 도달 시 즉각 전량 매도**하는 기계적 손절을 명시하십시오.

한국어로 전문적인 퀀트 리포트 양식에 맞춰 출력하십시오.
"""
    elif track == 'Track D':
        prompt = f"""{base_guideline}
당신은 실리콘밸리 톱티어 VC 출신의 공격적 테크 투자 애널리스트입니다.
아래 종목은 실리콘밸리 스마트 머니(Track D)가 베팅한 고성장/디럽티브 테크주입니다. 현재 적자이거나 부채율이 높을 수 있으나 이는 초기 시장 침투를 위한 레버리지입니다.

[분석 대상 종목 데이터]
- 티커: {ticker} ({name})
- 표기 소속 섹터: {sector}
- 재무 건전성: 기관 지분율 {inst_own:.1f}%, 잉여현금흐름(FCF) ${fcf:,.0f}
- 밸류에이션 지표: P/E {pe:.2f}, PEG {peg:.2f}, EV/EBITDA {ev_ebitda:.2f} ({pos_52w_str})
- 기술적 타점: {signal} (파동 요약: {candidate.get('stoch_summary', '')})
- 거래량 상태: 20일 평균 대비 {vol_ratio:.2f}배

[작성 요구사항]
1. 현재의 적자/고평가 논란을 넘어, 이 기업이 가진 기술적 해자(Moat)와 파괴적 혁신 내러티브가 시장을 어떻게 잠식하고 있는지 2문장으로 압축하십시오.
2. 기관 및 VC의 매집 평단가와 현재 기술적 파동 타점을 비교하여 상승 촉매제(Catalyst)의 폭발력을 평가하십시오.
3. 실전 매매 전략: 포트폴리오의 **위성 자산(Satellite Asset)**으로서 총 투자금의 **5%~10% 비중(High-Risk 관리)**으로만 접근할 것을 권고하고, **진입가 대비 -{stop_loss_pct}% 도달 시 즉시 전량 매도**하는 타이트하고 보수적인 손절 수칙을 강력히 제시하십시오.

한국어로 전문적인 퀀트 리포트 양식에 맞춰 출력하십시오.
"""
    else:
        sector_info = f"해당 종목은 현재 속한 섹터({sector})에 있습니다."
        if leading_sectors:
            # 매핑 호환 명칭을 고려하여 leading_sectors 포함 여부 유연 판단
            is_lead = any(s.lower() in sector.lower() or sector.lower() in s.lower() for s in leading_sectors)
            if is_lead:
                sector_info = f"🔥 **특별 프리미엄**: 이 종목은 현재 시장 자금 유입 최상위 주도 섹터인 **[{sector}]**에 속해 있어 강력한 순환매 수혜가 기대됩니다."
            
        prompt = f"""{base_guideline}
당신은 월스트리트의 상위 1% 헤지펀드 퀀트 애널리스트이자 리스크 매니저입니다.
아래의 정량적 필터링을 통과한 미국 주식 종목에 대해 심층 검증 리포트를 작성하십시오.

[분석 대상 종목 데이터]
- 티커: {ticker} ({name})
- 표기 소속 섹터: {sector}
- 재무 건전성: 기관 지분율 {inst_own:.1f}%, 잉여현금흐름(FCF) ${fcf:,.0f}
- 밸류에이션 지표: P/E {pe:.2f}, PEG {peg:.2f}, EV/EBITDA {ev_ebitda:.2f} ({pos_52w_str})
- 기술적 타점: {signal} (파동 요약: {candidate.get('stoch_summary', '')})
- 거래량 상태: 20일 평균 대비 {vol_ratio:.2f}배
- 섹터 분석: {sector_info}

[작성 요구사항]
1. **투자 핵심 요약**: 이 종목이 현재 매수/관망하기에 적합한 이유를 가치/성장성 관점과 함께 2문장으로 압축.
2. **상승 촉매제 (Catalyst)**: 해당 섹터 및 종목의 최근 기대되는 모멘텀이나 펀더멘털 강점 추론.
3. **잠재적 리스크 및 밸류에이션 평가**: 현재 P/E가 역사적 평균 대비 과도한 프리미엄 상태인지 여부를 반드시 객관적으로 분석하고, 저거래량 구간 표류 위험성을 명시.
4. **실전 매매 전략**: 총 투자금 대비 10~20% 내외의 현실적인 분할 진입 비중, 구체적 청산 타점 및 **진입가 대비 -{stop_loss_pct}% 도달 시 즉각 매도**하는 단일화된 기계적 손절 라인을 명확히 제시하십시오.

한국어로 전문적인 퀀트 리포트 양식에 맞춰 출력하십시오.
"""
    
    print(f"🤖 [4단계: AI 내러티브 분석] Ollama 기반 {ticker} 브리핑 생성 중...")
    ai_response = call_ollama(prompt)
    
    result = dict(candidate)
    result['ai_briefing'] = ai_response
    return result


def run_ai_verification(candidates, leading_sectors=None):
    """
    시그널이 포착된 후보군 전체를 대상으로 AI 브리핑 리스트를 생성합니다.
    """
    target_candidates = [c for c in candidates if "매수" in c.get('signal', '') or "폭발" in c.get('signal', '')]
    
    if not target_candidates:
        target_candidates = candidates[:2]
        
    final_reports = []
    for item in target_candidates:
        report = generate_ai_narrative(item, leading_sectors)
        final_reports.append(report)
        
    return final_reports


if __name__ == "__main__":
    sample = [{
        'ticker': 'AAPL', 
        'name': 'Apple Inc.', 
        'signal': '🔥 찐폭발 (강력매수)', 
        'inst_own': 65.2, 
        'fcf': 101000000000, 
        'vol_ratio': 0.8,
        'sector': 'Technology',
        'stoch_summary': 'S:▲ M:▲ L:▲'
    }]
    res = run_ai_verification(sample, leading_sectors=['Technology'])
    print(res[0]['ai_briefing'])
