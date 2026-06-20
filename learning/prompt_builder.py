# ==============================================================================
# [AI Trading Agent] 프롬프트 조립기 (learning/prompt_builder.py)
# ==============================================================================
# 로컬 AI(Gemma-2)가 메타인지(Meta-cognition)를 가질 수 있도록 기본 지침서에
# DB 내의 활성 규칙 및 최근 30일간의 실제 적중률 성과 보드를 동적으로 합성합니다.

import sqlite3
import sys
import os

# 프로젝트 루트 디렉토리 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from learning.db import get_connection

def get_recent_performance_stats() -> dict:
    """DB에서 최근 30일간의 적중률, 평균 수익률 및 최다 위반 오류 내역을 집계합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    
    stats = {}
    try:
        # 최근 20일 경과 기준 outcomes 데이터의 통계 연산 (degraded 제외)
        cursor.execute("""
            SELECT 
                COUNT(*) as total_samples,
                AVG(o.return_pct) as avg_ret,
                SUM(CASE WHEN o.outcome = 'win' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rt
            FROM outcomes o
            JOIN reports r ON o.report_id = r.id
            WHERE o.created_at >= date('now', '-30 days') AND o.days_elapsed = 20
              AND COALESCE(r.is_degraded, 0) = 0
        """)
        row = cursor.fetchone()
        
        if row and row[0] and row[0] > 0:
            stats["total_samples"] = int(row[0])
            stats["avg_return"] = float(row[1]) if row[1] else 0.0
            stats["win_rate"] = float(row[2]) if row[2] else 0.0
        else:
            stats["total_samples"] = 0
            
        # 가장 자주 위반되는 1순위 규칙ID 집계
        cursor.execute("""
            SELECT rule_id, rule_name, COUNT(*) as freq
            FROM validations
            WHERE created_at >= date('now', '-30 days')
            GROUP BY rule_id
            ORDER BY freq DESC
            LIMIT 1
        """)
        violation_row = cursor.fetchone()
        if violation_row:
            stats["top_violation"] = f"{violation_row[0]}({violation_row[1]}) [위반 {violation_row[2]}회]"
        else:
            stats["top_violation"] = "없음"
            
    except Exception as e:
        print(f"   ⚠️ [prompt_builder.py] 최근 성과 연산 오류: {e}")
        
    conn.close()
    return stats

def load_active_learned_rules_text() -> str:
    """DB에 적재 및 승인된 모든 활성 진화 규칙을 프롬프트용 텍스트 리스트로 빌드합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    
    learned_section = ""
    try:
        cursor.execute("""
            SELECT rule_id, rule_text 
            FROM learned_rules 
            WHERE status = 'active'
            ORDER BY live_alpha DESC, rule_id ASC
        """)
        rows = cursor.fetchall()
        
        if rows:
            learned_section = "\n\n## 🧬 [자가 학습에 의한 추가 강제 규칙 (Strict Constraints)]\n"
            learned_section += "춘식이가 과거의 오류와 투자 적중 성과 추적 결과로부터 **스스로 진화 도출하여 자가 승인한 특수 컴플라이언스 규칙**입니다. 반드시 100% 반영하십시오:\n\n"
            for rule_id, rule_text in rows:
                learned_section += f"- **[{rule_id}]** {rule_text}\n"
    except Exception as e:
        print(f"   ⚠️ [prompt_builder.py] 활성 진화 규칙 로드 실패: {e}")
        
    conn.close()
    return learned_section

def build_system_prompt(base_guideline: str) -> str:
    """
    기본 지침 프롬프트에 활성 자기진화 규칙 및 메타 성능 통계 보드를
    유기적으로 조립하여 젬마4에 주입될 최종 동적 시스템 지침서를 구성합니다.
    """
    # 1. DB에서 진화 및 활성화된 규칙 로드
    learned_rules_text = load_active_learned_rules_text()
    
    # 2. 최근 30일 피드백 통계 리포팅
    stats = get_recent_performance_stats()
    stats_section = ""
    if stats and stats.get("total_samples", 0) > 0:
        stats_section = f"""\n\n## 📡 [춘식이 자가 메타인지 성능 지표 (최근 30일)]
- **실전 20일 영업일 적중률**: {stats['win_rate']:.1f}%
- **20일 영업일 평균 수익률**: {stats['avg_return']:+.2f}%
- **가장 취약한 1순위 위반 규정**: {stats['top_violation']}
*주의: 위 취약 오류가 이번 리포트 작성 과정에서 재발하지 않도록 각별히 팩트 왜곡 방지에 유의하십시오.*"""

    # 3. 최종 조립된 프롬프트 반환
    return base_guideline + learned_rules_text + stats_section
