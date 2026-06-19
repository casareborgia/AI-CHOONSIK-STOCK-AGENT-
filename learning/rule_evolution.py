# ==============================================================================
# [AI Trading Agent] 모듈 C: 자기 진화 엔진 (learning/rule_evolution.py)
# ==============================================================================
# 과거 검증 위반 데이터 및 5/10/20 영업일 수익률 데이터를 결합 분석하여, 
# 춘식이의 추론 정확도를 극대화할 최적의 정량 규칙을 Gemma-2로 자동 생성/보완합니다.

import sqlite3
import json
import re
import os
import sys

# 프로젝트 루트 디렉토리 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from learning.db import get_connection
from core.ai_verify import call_ollama

def analyze_violation_patterns() -> list[dict]:
    """최근 30일간 반복적으로 발생한 위반 빈도수를 순위 매겨 제안 요소를 추출합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT rule_id, rule_name, COUNT(*) as freq, severity
        FROM validations
        WHERE created_at >= date('now', '-30 days')
        GROUP BY rule_id
        ORDER BY freq DESC
    """)
    patterns = cursor.fetchall()
    conn.close()
    
    suggestions = []
    for rule_id, rule_name, freq, severity in patterns:
        if freq >= 3:  # 최소 3회 이상 동일 오류 반복 시 진화 필요 제안
            suggestions.append({
                "rule_id": rule_id,
                "rule_name": rule_name,
                "freq": freq,
                "severity": severity,
                "message": f"오류 규칙 {rule_id}({rule_name})이 총 {freq}회 반복 발생했습니다. 프롬프트 내 예외 지침 보강이 강하게 요구됩니다."
            })
    return suggestions

def measure_rule_effectiveness() -> dict:
    """자동 교정된 리포트 집단과 원본 리포트 집단 간의 실제 투자 적중률(Win Rate)과 수익률 변위를 비교합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 20일 영업일 경과 성과 기준 비교 분석
    cursor.execute("""
        SELECT 
            CASE WHEN v.auto_fixed = 1 THEN 'auto_fixed' ELSE 'original' END as group_type,
            AVG(o.return_pct) as avg_return,
            SUM(CASE WHEN o.outcome = 'win' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate,
            COUNT(*) as sample_size
        FROM outcomes o
        JOIN reports r ON o.report_id = r.id
        LEFT JOIN validations v ON r.id = v.report_id
        WHERE o.days_elapsed = 20
        GROUP BY group_type
    """)
    rows = cursor.fetchall()
    conn.close()
    
    stats = {"auto_fixed": {"win_rate": 0.0, "avg_return": 0.0, "size": 0},
             "original": {"win_rate": 0.0, "avg_return": 0.0, "size": 0}}
             
    for g_type, avg_ret, win_rt, size in rows:
        if g_type in stats:
            stats[g_type]["win_rate"] = float(win_rt) if win_rt else 0.0
            stats[g_type]["avg_return"] = float(avg_ret) if avg_ret else 0.0
            stats[g_type]["size"] = int(size) if size else 0
            
    return stats

def get_next_rule_id() -> str:
    """DB 내의 기존 규칙 ID를 분석하여 R101, R102 등 100번대 신규 고유 ID를 부여합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    # 'R' + 숫자 형태(예: R101)만 대상으로 하여 R1A_FOO 같은 비정형 ID가 섞여도
    # int() 변환 시 ValueError로 크래시하지 않도록 한다.
    cursor.execute("SELECT rule_id FROM learned_rules WHERE rule_id LIKE 'R1%'")
    rows = cursor.fetchall()
    conn.close()

    max_num = 100  # 기본 시작점(다음 ID는 R101)
    for r in rows:
        rid = r[0]
        suffix = rid[1:] if rid and rid.startswith("R") else ""
        if suffix.isdigit():
            max_num = max(max_num, int(suffix))
    return f"R{max_num + 1}"

def save_learned_rule(rule_id: str, rule_text: str, check_condition: str) -> bool:
    """
    진화된 신규 규칙을 DB에 승인 대기 상태(is_active = FALSE)로 안전하게 적재합니다.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # 안전한 머신-휴먼 크로스체크를 위해 is_active = 0 (기본값)으로 추가
        cursor.execute("""
            INSERT INTO learned_rules (rule_id, rule_text, source, trigger_count, effectiveness, is_active)
            VALUES (?, ?, ?, 0, 0.0, 0)
        """, (rule_id, f"[{check_condition}] -> {rule_text}", "evolution"))
        conn.commit()
        print(f"   💾 [rule_evolution.py] AI 진화 규칙 {rule_id}가 승인 대기 상태(is_active=0)로 DB에 안전 적재되었습니다!")
        conn.close()
        return True
    except Exception as e:
        print(f"   ⚠️ [rule_evolution.py] 규칙 DB 적재 에러: {e}")
        conn.close()
        return False

def run_weekly_evolution():
    """
    스케줄러에 의해 정기 가동되는 메인 진화 파이프라인입니다.
    빈도 분석과 성과 지표를 AI Gemma-2에 피딩하여, 개선에 필요한 무결한 정량 규칙을 스스로 도출시킵니다.
    """
    print("\n🧬 [rule_evolution.py] 춘식이 자기진화 엔진 가동 시작...")
    
    # 1. 반복 에러 유형 및 성과 분석 수집
    violations = analyze_violation_patterns()
    performance = measure_rule_effectiveness()
    
    if not violations and performance["auto_fixed"]["size"] < 3:
        print("   📡 [rule_evolution.py] 진화 분석에 필요한 샘플 데이터 부족으로 진화를 연기합니다.")
        return
        
    next_id = get_next_rule_id()
    
    # 2. Gemma-2 진화 지침 프롬프트 작성
    prompt = f"""[투자 알고리즘 자기 진화 관리 지침서]
당신은 투자 AI 춘식이의 리포트 신뢰성을 지적하고 보강하는 고수준 퀀트 아키텍트입니다.
과거 리포트가 위반한 오류 패턴 및 실제 20일 뒤의 성과 분석 데이터를 참고하여, 다음 리포트의 가치 판단 누수를 철저히 차단할 '새로운 1개의 정량 검사 규칙'을 정교하게 도출하십시오.

## [과거 30일 위반 유형 데이터]
{json.dumps(violations, ensure_ascii=False, indent=2) if violations else "특이 반복 위반 없음"}

## [자동 보정 vs 원본 리포트 20일 수익률 대조군 성과]
- AI 교정군 (Auto Fixed): 적중률 {performance['auto_fixed']['win_rate']:.1f}% (평균수익률: {performance['auto_fixed']['avg_return']:+.2f}%)
- AI 원본군 (Original):   적중률 {performance['original']['win_rate']:.1f}% (평균수익률: {performance['original']['avg_return']:+.2f}%)

## [작성 규칙 스펙 (100% 준수)]
1. 새로 제안할 규칙 ID는 **{next_id}** 로 부여하십시오.
2. 분석 텍스트에서 모호한 지침을 피하고, 철저히 정량적(예: P/E, PEG, 52주고점대비%, 거래량, 기관지분율 등) 기준의 '조건-행동' 논리로 설계하십시오.
3. 생성된 규칙은 주관적 서술을 엄금하고 단일하고 명료한 키워드와 함께 설계하십시오.
4. 반드시 완벽한 JSON 포맷 1개만으로 결과물을 리턴하십시오. 부가 설명이나 서론, 결론, 마크다운 코드 블록(```)을 리턴하지 마십시오.

## [출력 JSON 포맷 예시]
{{"rule_id": "{next_id}", "check_condition": "P/E가 40을 초과하고 52주 고점 대비 -5% 이내인 고평가 상태", "rule_text": "리포트에 '밸류에이션 부담' 혹은 '상방 저항' 키워드가 누락된 경우 경고를 추가하고 매수 등급을 하향 검토할 것", "required_keywords": ["밸류에이션 부담", "상방 저항"]}}

출력 JSON:"""
    
    # 3. AI 호출 및 JSON 정밀 파싱
    ai_response = call_ollama(prompt)
    
    # 마크다운 코드 블록 제거 및 순수 JSON 추출 헬퍼
    clean_json = ai_response.strip()
    if "```json" in clean_json:
        clean_json = clean_json.split("```json")[1].split("```")[0].strip()
    elif "```" in clean_json:
        clean_json = clean_json.split("```")[1].split("```")[0].strip()
        
    try:
        rule_data = json.loads(clean_json)
        rule_id = rule_data.get("rule_id", next_id)
        rule_text = rule_data.get("rule_text", "")
        check_condition = rule_data.get("check_condition", "")
        
        if rule_text and check_condition:
            # 4. DB에 적재
            save_learned_rule(rule_id, rule_text, check_condition)
        else:
            print("   ⚠️ [rule_evolution.py] AI 출력 JSON 내 필수 필드가 누락되었습니다.")
    except Exception as e:
        print(f"   ⚠️ [rule_evolution.py] AI 응답 JSON 파싱 실패: {e}\n   AI 원문:\n{ai_response}")
