# ==============================================================================
# [AI Trading Agent] 모듈 A: 리포트 자동 검증 엔진 (learning/validator.py)
# ==============================================================================
# 리포트 생성 직후 6대 정량 규칙 및 SQLite 내의 동적 학습 규칙을 검증하고,
# 위반 사항 발견 시 Ollama(Gemma-2)를 사용하여 전문적으로 리포트를 자동 교정합니다.

import sqlite3
import re
import os
import sys

# 프로젝트 루트 디렉토리 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from learning.db import get_connection
from core.ai_verify import call_ollama

def get_sector_avg_pe(sector_name: str) -> float:
    """DB에서 해당 섹터의 최근 평균 P/E를 가져옵니다. 없을 시 기본값 20.0을 사용합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # yfinance나 finviz의 섹터명과 DB의 섹터명 유사도 검색
    cursor.execute("""
        SELECT avg_pe FROM sector_valuations 
        WHERE ? LIKE '%' || sector || '%' OR sector LIKE '%' || ? || '%'
        LIMIT 1
    """, (sector_name, sector_name))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return float(row[0])
    return 20.0  # 기본 폴백 값

def load_active_learned_rules() -> list[dict]:
    """DB에서 활성화된 자동 진화 규칙 리스트를 가져옵니다."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT rule_id, rule_text FROM learned_rules WHERE is_active = 1")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def evaluate_learned_rule(rule: dict, report_data: dict) -> dict:
    """
    자동 생성된 learned_rules 검증을 집행합니다.
    규칙 포맷 예시: {"rule_id": "R101", "rule_text": "P/E가 50 초과인 기술주의 경우 고평가 키워드 언급"}
    """
    rule_id = rule["rule_id"]
    rule_text = rule["rule_text"]
    report_text = report_data["report_text"]
    
    # 텍스트에 포함된 수치 조건이나 키워드 매칭 형태의 동적 검증
    # 만약 AI가 생성해 둔 규칙에 핵심 키워드가 누락되어 있는지 러프하게 파싱하여 진단합니다.
    # [예외/유연 검증] 춘식이가 똑똑하게 진단하기 위해 텍스트 기반 휴리스틱 매칭
    
    # 예시: 특정 키워드 누락 검출
    # 규칙 본문에 요구되는 단어들이 리포트 원문에 들어있는지 확인
    keywords_match = re.findall(r"['\"](.*?)['\"]", rule_text)
    if not keywords_match:
        keywords_match = [w for w in ["주의", "리스크", "거품", "괴리", "보수적"] if w in rule_text]
        
    missing_kws = [kw for kw in keywords_match if kw not in report_text]
    
    # 간단한 정량 조건 매칭 (예: P/E > 40)
    pe_limit_match = re.search(r"P/E\s*(?:이상|초과|>\s*|>=)(\d+)", rule_text)
    if pe_limit_match:
        pe_limit = float(pe_limit_match.group(1))
        if report_data["pe_ratio"] > pe_limit and missing_kws:
            return {
                "rule_id": rule_id,
                "rule_name": f"학습 규칙 {rule_id} 위반",
                "severity": "warning",
                "description": f"학습된 지침 [{rule_text}]에 의해 필수적인 언급이 리포트에 누락되었습니다."
            }
            
    return None

def validate_report(report_data: dict) -> list[dict]:
    """
    순수 Python 로직으로 6대 핵심 정량 지표 정합성 검사를 매우 빠르게 실행합니다.
    """
    violations = []
    report_text = report_data.get("report_text", "")
    
    # --- [규칙 1] P/E 과열 경고 누락 (R001) ---
    sector_avg_pe = get_sector_avg_pe(report_data.get("sector", "Unknown"))
    pe = report_data.get("pe_ratio", 0.0)
    
    if pe > sector_avg_pe * 2:
        kws = ["이익 압착", "earnings compression", "밸류에이션 왜곡", "고평가", "compressed"]
        if not any(kw in report_text.lower() for kw in kws):
            violations.append({
                "rule_id": "R001",
                "rule_name": "P/E 과열 경고 누락",
                "severity": "critical",
                "description": f"P/E({pe:.1f})가 섹터 평균({sector_avg_pe:.1f})의 2배를 초과하나, 리포트에 이익 압착/밸류에이션 왜곡에 대한 경고가 없습니다."
            })
            
    # --- [규칙 2] 기관 지분율 착시 경고 누락 (R002) ---
    inst_own = report_data.get("inst_ownership", 0.0)
    if inst_own > 90:
        kws = ["공매도", "숏스퀴즈", "착시", "대차", "short interest", "squeeze"]
        if not any(kw in report_text.lower() for kw in kws):
            violations.append({
                "rule_id": "R002",
                "rule_name": "기관 지분율 착시 경고 누락",
                "severity": "critical",
                "description": f"기관 지분율({inst_own:.1f}%)이 90%를 초과하는 극단적 상태이나, 공매도 이중 대차로 인한 지분 착시 가능성 경고가 누락되었습니다."
            })
            
    # --- [규칙 3] 시그널-펀더멘털 정합성 위반 (R003) ---
    signal = report_data.get("signal_label", "")
    is_strong_buy = any(word in signal for word in ["매수", "폭발", "surge", "buy"])
    if is_strong_buy and pe > sector_avg_pe * 3:
        kws = ["괴리", "고평가 주의", "밸류에이션 리스크", "비중 조절"]
        if not any(kw in report_text for kw in kws):
            violations.append({
                "rule_id": "R003",
                "rule_name": "시그널-펀더멘털 괴리 미언급",
                "severity": "critical",
                "description": f"강력매수 시그널({signal})이나 P/E({pe:.1f})가 섹터 평균의 3배를 초과하는 극단적 고평가 상태입니다. 기술적 이격과 기본 가치 사이의 괴리 지적이 누락되었습니다."
            })
            
    # --- [규칙 4] 52주 고점 근접 + 저거래량 위험 해석 누락 (R004) ---
    close = report_data.get("close_price", 0.0)
    high_52w = report_data.get("high_52w", 0.0)
    vol_ratio = report_data.get("vol_ratio", 1.0)
    
    if high_52w > 0:
        pct_from_high = ((high_52w - close) / high_52w) * 100
        if pct_from_high < 5 and vol_ratio < 1.2:
            kws = ["유동성 고갈", "에너지 소진", "추세 약화", "상방 돌파 실패"]
            if not any(kw in report_text for kw in kws):
                violations.append({
                    "rule_id": "R004",
                    "rule_name": "고점 근접 저거래량 위험 해석 누락",
                    "severity": "warning",
                    "description": f"52주 고점 대비 단 -{pct_from_high:.1f}% 근접했으나 거래량 배수가 {vol_ratio:.2f}x로 매우 낮습니다. 유동성 고갈 및 돌파 동력 부족 리스크 지적이 없습니다."
                })
                
    # --- [규칙 5] 섹터 집중도 경고 누락 (R005) ---
    all_cands = report_data.get("all_candidates", [])
    if all_cands:
        current_sector = report_data.get("sector", "Unknown")
        sector_counts = 0
        for c in all_cands:
            c_sec = c.get("disp_sector", c.get("sector", "Unknown"))
            if c_sec == current_sector:
                sector_counts += 1
                
        total = len(all_cands)
        if total > 0 and (sector_counts / total) >= 0.6:
            kws = ["섹터 집중", "집중 리스크", "쏠림", "분산 투자"]
            if not any(kw in report_text for kw in kws):
                violations.append({
                    "rule_id": "R005",
                    "rule_name": "섹터 집중 리스크 경고 누락",
                    "severity": "warning",
                    "description": f"전체 분석 후보 종목 중 {current_sector} 섹터가 {sector_counts}/{total}({sector_counts/total*100:.0f}%)를 차지하여 과도한 쏠림이 보이나, 섹터 집중 리스크 경고가 생략되었습니다."
                })
                
    # --- [규칙 6] PEG만으로 저평가 단정 및 맹신 (R006) ---
    peg = report_data.get("peg_ratio", 0.0)
    if peg is not None and 0 < peg < 1.0:
        if pe > sector_avg_pe * 1.5:
            kws = ["기저효과", "이익의 질", "earnings quality", "왜곡", "일시적"]
            if not any(kw in report_text.lower() for kw in kws):
                violations.append({
                    "rule_id": "R006",
                    "rule_name": "PEG 맹신 경고 누락",
                    "severity": "warning",
                    "description": f"PEG({peg:.2f})는 수치상 저평가를 시사하나 P/E({pe:.1f})는 섹터 평균을 대폭 웃돕니다. 일시적 이익 기저효과 및 이익의 질(Quality of Earnings) 왜곡 리스크 언급이 없습니다."
                })
                
    # --- DB에서 학습된 동적 규칙 평가 및 결합 ---
    try:
        learned_rules = load_active_learned_rules()
        for rule in learned_rules:
            res = evaluate_learned_rule(rule, report_data)
            if res:
                violations.append(res)
    except Exception as e:
        print(f"   ⚠️ [validator.py] DB 동적 규칙 로드 실패: {e}")
        
    return violations

def auto_fix_report(original_report: str, violations: list[dict]) -> str:
    """
    규칙 위반 내용을 젬마4(Gemma-2) 모델에 송신하여, 문맥의 왜곡 없이 리포트를 전문적으로 재수정합니다.
    """
    critical = [v for v in violations if v["severity"] == "critical"]
    warnings = [v for v in violations if v["severity"] == "warning"]
    
    if not critical and not warnings:
        return original_report
        
    critical_text = "\n".join([f"- [{v['rule_id']}] {v['description']}" for v in critical]) if critical else "없음"
    warning_text = "\n".join([f"- [{v['rule_id']}] {v['description']}" for v in warnings]) if warnings else "없음"
    
    # 교정 극대화 프롬프트
    fix_prompt = f"""[명령서: 투자 보고서 퀄리티 정밀 교정 지침]
당신은 세계적인 헤지펀드의 컴플라이언스 및 리스크 총괄 위원입니다.
AI가 작성한 원문 보고서에서 투자자에게 치명적인 손실을 안길 수 있는 정량적 사실 왜곡 및 리스크 누락 규칙 위반이 감지되었습니다. 

지침에 따라 보고서를 정밀하게 교정(Revision)하십시오.

## [검증 위반 감지 내역]
1. 치명적 위반 (반드시 보고서 수정 반영):
{critical_text}

2. 경고 및 주의 추가 권고 (보고서에 관련 단락/문구 삽입):
{warning_text}

## [절대 준수 교정 규칙]
1. 원문 보고서의 전문적인 마크다운 포맷과 핵심 골격을 **100% 보존**하십시오.
2. 치명적 위반(Critical)은 감지된 사실 데이터(P/E, 수급 등)를 기반으로 해당 논평 섹션의 가치관이나 해석을 객관적 리스크 중심으로 직접 재수정하십시오.
3. 경고 및 주의 권고(Warning)는 해당 종목의 리스크 섹션(또는 마지막 부분)에 구체적인 문장으로 균형 잡힌 시각을 추가하십시오.
4. 새로운 할루시네이션(과거 날짜, 존재하지 않는 수급 재료 등)을 절대로 창작하여 끼워넣지 마십시오. 오로지 주어지고 검증된 사실 왜곡의 정밀 교정만을 목표로 합니다.
5. 보고서 원본 내용은 수정된 문장을 제외하고는 한 글자도 바꾸지 마십시오.

## [교정 대상 원문 투자 리포트]
{original_report}

---
수정 및 보정이 끝난 마크다운 보고서 전문만을 출력하십시오:"""
    
    print("   🛡️ [validator.py] 규칙 위반 발생에 따른 Gemma-2 정밀 보정 기동...")
    revised_report = call_ollama(fix_prompt, model_type="light")
    
    # 젬마의 응답에 에러나 통신 실패가 있으면 안전하게 원본을 반환
    if "⚠️ 로컬 AI 통신 실패" in revised_report or not revised_report.strip():
        print("   ⚠️ [validator.py] Gemma-2 통신 실패로 교정 보류 (원본 적용)")
        return original_report
        
    return revised_report
