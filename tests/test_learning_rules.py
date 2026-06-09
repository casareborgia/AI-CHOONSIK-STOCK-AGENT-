# ==============================================================================
# [단위 테스트] P1 자가학습 폐루프 연동 검증 (tests/test_learning_rules.py)
# ==============================================================================
# 자가진화 주기, 검증/성찰 규칙 분리, 텔레그램 승인/반려 워크플로, 성찰 부하 제한을 검증합니다.
#
# 실행:  python3 tests/test_learning_rules.py

import sys
import os
import sqlite3
import unittest
import asyncio

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from learning.db import (
    get_connection,
    get_system_meta,
    set_system_meta,
    get_pending_rules,
    approve_rule,
    reject_rule,
    init_db
)
from learning.validator import load_active_learned_rules, validate_report
from learning.reflection_engine import ReflectionEngine

class TestLearningRulesLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """테스트 데이터베이스 초기화 및 레거시 데이터 세팅"""
        # 1. 먼저 DB 연결을 맺고, 마이그레이션 전의 레거시 데이터 삽입
        conn = get_connection()
        cursor = conn.cursor()
        
        # 테스트 전 learned_rules 비우고 시작
        cursor.execute("DELETE FROM learned_rules WHERE rule_id LIKE 'T_%'")
        cursor.execute("DELETE FROM system_meta WHERE key LIKE 'T_%'")
        
        # REF_ 로 시작하는 성찰 데이터 (마이그레이션 전 상태인 outcome_analysis로 삽입)
        cursor.execute("""
            INSERT OR REPLACE INTO learned_rules (rule_id, rule_text, source, is_active)
            VALUES ('T_REF_AAPL_2025', '테스트 성찰 지침', 'outcome_analysis', 1)
        """)
        # R1 로 시작하는 진화 규칙 (마이그레이션 전 상태인 outcome_analysis로 삽입)
        cursor.execute("""
            INSERT OR REPLACE INTO learned_rules (rule_id, rule_text, source, is_active)
            VALUES ('T_R109', '테스트 진화 규칙', 'outcome_analysis', 0)
        """)
        
        conn.commit()
        conn.close()
        
        # 2. 이제 init_db()를 호출하여 learned_rules 마이그레이션 실행
        init_db()

    def test_1_system_meta_crud(self):
        """1. system_meta 설정값 읽고 쓰기 검증"""
        test_key = "T_last_evolution"
        test_val = "2025-01-01"
        
        # 저장 및 조회
        set_system_meta(test_key, test_val)
        fetched = get_system_meta(test_key)
        self.assertEqual(fetched, test_val)
        
        # 존재하지 않는 키 조회
        self.assertIsNone(get_system_meta("T_NON_EXIST"))

    def test_2_source_reclassification(self):
        """2. 레거시 규칙 재분류 마이그레이션 검증"""
        # 마이그레이션이 이미 init_db() 호출로 이루어졌으므로 DB 조회 확인
        conn = get_connection()
        cursor = conn.cursor()
        
        # REF_ 접두사는 reflection으로
        cursor.execute("SELECT source FROM learned_rules WHERE rule_id = 'T_REF_AAPL_2025'")
        row_ref = cursor.fetchone()
        self.assertIsNotNone(row_ref)
        self.assertEqual(row_ref[0], "reflection")
        
        # R1 접두사는 evolution으로
        cursor.execute("SELECT source FROM learned_rules WHERE rule_id = 'T_R109'")
        row_evo = cursor.fetchone()
        self.assertIsNotNone(row_evo)
        self.assertEqual(row_evo[0], "evolution")
        
        conn.close()

    def test_3_rule_approval_workflow(self):
        """3. 텔레그램 승인/반려 DB 액션 검증"""
        # 3-1. 대기 규칙 리스트에 T_R109가 올라와 있는지 확인
        pending = get_pending_rules()
        pending_ids = [r["rule_id"] for r in pending]
        self.assertIn("T_R109", pending_ids)
        
        # 3-2. 승인(approve) 액션 수행 -> is_active = 1 검증
        approve_success = approve_rule("T_R109")
        self.assertTrue(approve_success)
        
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM learned_rules WHERE rule_id = 'T_R109'")
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        
        # 3-3. 반려(reject) 액션 수행 -> DB 삭제 검증
        reject_success = reject_rule("T_R109")
        self.assertTrue(reject_success)
        
        cursor.execute("SELECT COUNT(*) FROM learned_rules WHERE rule_id = 'T_R109'")
        count = cursor.fetchone()[0]
        self.assertEqual(count, 0)
        conn.close()

    def test_4_validator_evolution_filter(self):
        """4. validator가 evolution 규칙만 선별해 검증에 쓰는지 검증"""
        conn = get_connection()
        cursor = conn.cursor()
        
        # 4-1. evolution 규칙 활성화 추가
        cursor.execute("""
            INSERT OR REPLACE INTO learned_rules (rule_id, rule_text, source, is_active)
            VALUES ('T_R999', 'P/E >=40일 경우 "주의" 단어 필수 포함', 'evolution', 1)
        """)
        
        # 4-2. reflection 규칙도 활성화 추가 (오탐 유발 조건)
        cursor.execute("""
            INSERT OR REPLACE INTO learned_rules (rule_id, rule_text, source, is_active)
            VALUES ('T_REF_999', '성과 성찰 지침서 본문', 'reflection', 1)
        """)
        conn.commit()
        conn.close()
        
        # 4-3. 활성 규칙 로드 시 reflection은 배제되고 T_R999만 포함되는지 확인
        active_rules = load_active_learned_rules()
        rule_ids = [r["rule_id"] for r in active_rules]
        self.assertIn("T_R999", rule_ids)
        self.assertNotIn("T_REF_999", rule_ids)
        
        # 4-4. 실제 validate_report 구동을 통한 규칙 검증
        report_data = {
            "ticker": "TSLA",
            "sector": "Consumer Discretionary",
            "pe_ratio": 45.0,
            "report_text": "테스트용 리포트 본문이며, 조심해야 할 단어는 빠져 있습니다."
        }
        violations = validate_report(report_data)
        violation_rules = [v["rule_id"] for v in violations]
        self.assertIn("T_R999", violation_rules)
        self.assertNotIn("T_REF_999", violation_rules)

    def test_5_reflection_concurrency_limit(self):
        """5. 성찰 처리량 증가 및 동시성 세마포어 적용 검증"""
        engine = ReflectionEngine(concurrency=3)
        self.assertTrue(hasattr(engine, "semaphore"))
        self.assertIsInstance(engine.semaphore, asyncio.Semaphore)
        
        # get_pending_reports 쿼리 한도 상향 확인
        # 쿼리가 LIMIT 15로 동작하는지 문자 확인
        import inspect
        source = inspect.getsource(engine.get_pending_reports)
        self.assertIn("LIMIT 15", source)

    @classmethod
    def tearDownClass(cls):
        """테스트 데이터 정리"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM learned_rules WHERE rule_id LIKE 'T_%'")
        cursor.execute("DELETE FROM system_meta WHERE key LIKE 'T_%'")
        conn.commit()
        conn.close()

if __name__ == "__main__":
    unittest.main()
