# ==============================================================================
# [AI Trading Agent] 단위 테스트: 지연 성찰 엔진 검증 (tests/test_reflection.py)
# ==============================================================================

import unittest
import sys
import os
import sqlite3
from datetime import datetime

# 프로젝트 루트 디렉토리를 path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from learning.db import get_connection
from learning.reflection_engine import ReflectionEngine

class TestReflectionEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """테스트용 임시 DB 테이블 생성 및 모크 데이터 세팅"""
        cls.db_path = "chunsik_learning.db"
        cls.engine = ReflectionEngine()
        
        # 테스트용 임의의 레포트 삽입
        conn = get_connection()
        cursor = conn.cursor()
        
        # 1. 가상의 테스트용 report 레코드 삽입 (이미 존재하는 테이블 활용)
        # 만약 outcomes에 이 report_id에 매칭되는 데이터가 없으면 pending으로 간주됨
        cls.test_ticker = "T_REF_TEST"
        cls.test_date = datetime.now().strftime("%Y-%m-%d")
        
        cursor.execute("""
            INSERT INTO reports (date, ticker, sector, signal_label, close_price, report_text)
            VALUES (?, ?, 'Technology', '🔥 찐폭발 (강력매수)', 100.0, 'This is a test report for reflection engine.')
        """, (cls.test_date, cls.test_ticker))
        
        cls.report_id = cursor.lastrowid
        conn.commit()
        conn.close()
        print(f"\n[setUp] Created test report record ID: {cls.report_id} for {cls.test_ticker}")

    def test_reflection_processing(self):
        """ReflectionEngine이 pending 상태의 리포트를 스캔하고 올바르게 Outcomes 및 Learned Rules를 적재하는지 검증"""
        # 1. pending 리포트에 방금 삽입한 테스트 건이 포함되어 있는지 확인
        pending_list = self.engine.get_pending_reports()
        pending_ids = [r[0] for r in pending_list]
        
        self.assertIn(self.report_id, pending_ids)
        print(f" -> Found pending report ID {self.report_id} in scan list.")

        # 2. save_reflection 메서드를 통한 DB 갱신 검증
        test_reflection = "테스트용 성찰 결과: P/E 과열 우려를 무시했으나 실적 성장이 이를 방어함."
        self.engine.save_reflection(
            report_id=self.report_id,
            ticker=self.test_ticker,
            entry_price=100.0,
            check_date=self.test_date,
            check_price=105.5,
            return_pct=5.5,
            outcome="win",
            reflection=test_reflection
        )

        # 3. DB Outcomes 저장 확인
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT outcome, return_pct FROM outcomes WHERE report_id = ?", (self.report_id,))
        outcome_row = cursor.fetchone()
        
        self.assertIsNotNone(outcome_row)
        self.assertEqual(outcome_row[0], "win")
        self.assertEqual(outcome_row[1], 5.5)
        print(f" -> Database 'outcomes' verified. Result: {outcome_row[0]}, Returns: {outcome_row[1]}%")

        # 4. DB Learned Rules 저장 확인
        cursor.execute("SELECT rule_text FROM learned_rules WHERE rule_id LIKE ?", (f"REF_{self.test_ticker}%",))
        rule_row = cursor.fetchone()
        
        self.assertIsNotNone(rule_row)
        self.assertIn("win", rule_row[0].lower())
        self.assertIn(test_reflection, rule_row[0])
        print(" -> Database 'learned_rules' verified. Reflection text found in prompt database.")

        conn.close()

    @classmethod
    def tearDownClass(cls):
        """테스트가 끝나면 삽입했던 임시 테스트 레코드 청소"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM outcomes WHERE report_id = ?", (cls.report_id,))
        cursor.execute("DELETE FROM reports WHERE id = ?", (cls.report_id,))
        cursor.execute("DELETE FROM learned_rules WHERE rule_id LIKE ?", (f"REF_{cls.test_ticker}%",))
        conn.commit()
        conn.close()
        print("[tearDown] Cleaned up temporary test database records.")


if __name__ == "__main__":
    unittest.main()
