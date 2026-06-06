# ==============================================================================
# [AI Trading Agent] 자기학습 DB 매니저 (learning/db.py)
# ==============================================================================
# SQLite 기반의 춘식이 학습 데이터베이스를 생성하고, 리포트 저장, 검증 결과 기록,
# 성과 추적 결과 저장 및 섹터 밸류에이션 관리를 위한 CRUD 인터페이스를 제공합니다.

import sqlite3
import os
from datetime import datetime

# 데이터베이스 파일 경로 설정 (프로젝트 루트 디렉토리 기준)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "chunsik_learning.db")

def get_connection():
    """SQLite 데이터베이스 커넥션을 반환합니다."""
    return sqlite3.connect(DB_PATH)

def init_db():
    """학습에 필요한 5대 테이블 스키마를 초기화합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. reports: 생성된 리포트 원문 및 기본 재무 메타데이터
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,                    -- 리포트 생성일 (YYYY-MM-DD)
        ticker TEXT NOT NULL,                  -- 종목 티커
        sector TEXT,                           -- 섹터명
        signal_label TEXT,                     -- 포착 시그널 (예: 찐폭발)
        entry_grade TEXT,                      -- 멀티타임프레임 타점 등급 (A~E)
        pe_ratio REAL,                         -- P/E
        peg_ratio REAL,                        -- PEG
        inst_ownership REAL,                   -- 기관 지분율 (%)
        close_price REAL,                      -- 당시 종가
        target_price REAL,                     -- 목표가
        stop_loss_pct REAL,                    -- 손절선 (%)
        report_text TEXT,                      -- 젬마4가 생성한 최초 원문 리포트
        revised_text TEXT,                     -- 자동 교정/보정 완료된 최종 리포트 (수정 없으면 NULL)
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # 2. validations: 모듈 A 검증 규칙 위반 및 교정 내역
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS validations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER NOT NULL,
        rule_id TEXT NOT NULL,                 -- R001, R002 등
        rule_name TEXT NOT NULL,               -- 규칙 명칭
        severity TEXT NOT NULL,                -- 'critical' | 'warning' | 'info'
        description TEXT NOT NULL,             -- 구체적인 위반 팩트 설명
        auto_fixed BOOLEAN DEFAULT FALSE,      -- Gemma-2로 자동 교정 여부
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (report_id) REFERENCES reports(id)
    );
    """)
    
    # 3. outcomes: 모듈 B 5/10/20 영업일 경과 시점의 성과 (Alpha 관련 신규 컬럼 보강)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS outcomes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER NOT NULL,
        ticker TEXT NOT NULL,
        entry_price REAL NOT NULL,
        check_date TEXT NOT NULL,              -- 종가 추적일
        check_price REAL NOT NULL,             -- 추적 시점 종가
        days_elapsed INTEGER NOT NULL,         -- 경과 영업일 (5, 10, 20)
        return_pct REAL NOT NULL,              -- 수익률 (%)
        hit_target BOOLEAN,                    -- 목표가 터치 여부
        hit_stoploss BOOLEAN,                  -- 손절선 터치 여부
        outcome TEXT NOT NULL,                 -- 'win' | 'loss' | 'hold' | 'stopped_out'
        benchmark_return_pct REAL,             -- 벤치마크 (SPY) 수익률 (%)
        alpha_return_pct REAL,                 -- 초과수익률 (%)
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (report_id) REFERENCES reports(id)
    );
    """)

    # outcomes 테이블 컬럼 마이그레이션
    cursor.execute("PRAGMA table_info(outcomes)")
    columns = [col[1] for col in cursor.fetchall()]
    if "benchmark_return_pct" not in columns:
        try:
            cursor.execute("ALTER TABLE outcomes ADD COLUMN benchmark_return_pct REAL")
            print("💾 [DB Migration] outcomes 테이블에 benchmark_return_pct 컬럼이 성공적으로 추가되었습니다.")
        except Exception as e:
            print(f"⚠️ [DB Migration] benchmark_return_pct 추가 실패: {e}")
            
    if "alpha_return_pct" not in columns:
        try:
            cursor.execute("ALTER TABLE outcomes ADD COLUMN alpha_return_pct REAL")
            print("💾 [DB Migration] outcomes 테이블에 alpha_return_pct 컬럼이 성공적으로 추가되었습니다.")
        except Exception as e:
            print(f"⚠️ [DB Migration] alpha_return_pct 추가 실패: {e}")
    
    # 4. learned_rules: 모듈 C 자동 진화 프롬프트 검증 규칙
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS learned_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_id TEXT UNIQUE NOT NULL,           -- R001, R002 등
        rule_text TEXT NOT NULL,                -- 규칙 지침서 본문
        source TEXT NOT NULL,                   -- 'manual' | 'auto_validation' | 'outcome_analysis'
        trigger_count INTEGER DEFAULT 0,        -- 검증 위반으로 발동된 횟수
        effectiveness REAL,                     -- 적용 후 성과 변동 영향도
        is_active BOOLEAN DEFAULT TRUE,         -- 실제 프롬프트 주입 활성화 여부
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # 5. sector_valuations: 정밀 과열 판정을 위한 시간에 따르는 섹터 평균 밸류에이션
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sector_valuations (
        sector TEXT PRIMARY KEY,
        avg_pe REAL NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 6. thesis_maps: 보유 중인 장기 투자 종목 및 투자 Thesis Map
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS thesis_maps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        investment_thesis TEXT NOT NULL,
        key_indicators TEXT NOT NULL,
        catalysts TEXT NOT NULL,
        risks TEXT NOT NULL,
        kill_condition TEXT NOT NULL,
        noise_rules TEXT NOT NULL,
        earnings_checkpoints TEXT NOT NULL,
        valuation_criteria TEXT NOT NULL,
        one_line_conclusion TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 7. knowledge_graph: 종목, 섹터, 매크로 변수 간의 다차원 연결 관계망
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS knowledge_graph (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL,             -- 'sector', 'ticker', 'macro_event'
        source_id TEXT NOT NULL,               -- 'Technology', 'AAPL', 'interest_rate'
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        relation_type TEXT NOT NULL,           -- 'belongs_to', 'affects_bullish', 'affects_bearish'
        weight REAL DEFAULT 1.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # 초기 주도/전통 섹터 평균 P/E 기본값 삽입 (테이블이 비어있을 때만)
    cursor.execute("SELECT COUNT(*) FROM sector_valuations")
    if cursor.fetchone()[0] == 0:
        default_valuations = [
            ('Technology', 30.0),
            ('Semiconductors', 32.0),
            ('Healthcare', 22.0),
            ('Financials', 14.0),
            ('Energy', 11.0),
            ('Consumer Discretionary', 24.0),
            ('Consumer Staples', 19.0),
            ('Industrials', 18.0),
            ('Materials', 16.0),
            ('Utilities', 15.0),
            ('Real Estate', 17.0),
            ('Communication Services', 20.0),
            ('Unknown', 20.0)
        ]
        cursor.executemany(
            "INSERT INTO sector_valuations (sector, avg_pe) VALUES (?, ?)", 
            default_valuations
        )
    
    conn.commit()
    conn.close()
    print("✅ [chunsik_learning.db] 6대 코어 데이터베이스 스키마 구축 완료.")

def save_report_to_db(stock: dict, raw_report: str, revised_report: str, entry_grade: str) -> int:
    """최종 분석된 리포트와 퀀트 메타데이터를 DB reports 테이블에 저장하고 생성된 ID를 반환합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    ticker = stock.get("ticker", "UNKNOWN")
    sector = stock.get("disp_sector", stock.get("sector", "Unknown"))
    signal = stock.get("signal", "관망")
    pe = stock.get("pe", 0.0)
    peg = stock.get("peg", 0.0)
    
    # 지분율 백분율 정규화 (소수점 형태일 경우 100을 곱함)
    inst_own = stock.get("inst_own", 0.0)
    if inst_own > 0 and inst_own < 1.0:
        inst_own *= 100
        
    close = stock.get("close", 0.0)
    
    # 동적 익절 목표가 (20% 익절 폴백) 및 손절가 계산
    beta = stock.get("beta", 1.0)
    if beta is None or beta <= 0:
        beta = 1.0
    stop_pct = float(round(max(5.0, min(12.0, 5.0 * beta))))
    
    target_price = stock.get("target_price", close * 1.20)
    
    cursor.execute("""
        INSERT INTO reports (
            date, ticker, sector, signal_label, entry_grade, pe_ratio, peg_ratio, 
            inst_ownership, close_price, target_price, stop_loss_pct, report_text, revised_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        today_str, ticker, sector, signal, entry_grade, pe, peg, 
        inst_own, close, target_price, stop_pct, raw_report, revised_report
    ))
    
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return report_id

def save_validation_results(report_id: int, violations: list[dict], auto_fixed: bool):
    """검증 오류 내역을 DB validations 테이블에 저장합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    
    for v in violations:
        cursor.execute("""
            INSERT INTO validations (report_id, rule_id, rule_name, severity, description, auto_fixed)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (report_id, v["rule_id"], v["rule_name"], v["severity"], v["description"], int(auto_fixed)))
        
        # 발동된 규칙 카운트 1 증가
        cursor.execute("""
            UPDATE learned_rules 
            SET trigger_count = trigger_count + 1 
            WHERE rule_id = ?
        """, (v["rule_id"],))
        
    conn.commit()
    conn.close()

def add_or_update_thesis(ticker: str, name: str, data: dict) -> bool:
    """관심 종목의 Thesis Map 데이터를 DB에 삽입하거나 갱신합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    success = False
    try:
        cursor.execute("""
            INSERT INTO thesis_maps (
                ticker, name, investment_thesis, key_indicators, catalysts, risks, 
                kill_condition, noise_rules, earnings_checkpoints, valuation_criteria, one_line_conclusion
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                name = excluded.name,
                investment_thesis = excluded.investment_thesis,
                key_indicators = excluded.key_indicators,
                catalysts = excluded.catalysts,
                risks = excluded.risks,
                kill_condition = excluded.kill_condition,
                noise_rules = excluded.noise_rules,
                earnings_checkpoints = excluded.earnings_checkpoints,
                valuation_criteria = excluded.valuation_criteria,
                one_line_conclusion = excluded.one_line_conclusion,
                updated_at = CURRENT_TIMESTAMP
        """, (
            ticker.upper(),
            name,
            data.get("investment_thesis", ""),
            data.get("key_indicators", ""),
            data.get("catalysts", ""),
            data.get("risks", ""),
            data.get("kill_condition", ""),
            data.get("noise_rules", ""),
            data.get("earnings_checkpoints", ""),
            data.get("valuation_criteria", ""),
            data.get("one_line_conclusion", "")
        ))
        conn.commit()
        success = True
    except Exception as e:
        print(f"⚠️ [learning/db.py] add_or_update_thesis 실패: {e}")
    finally:
        conn.close()
    return success

def get_thesis_map(ticker: str) -> dict:
    """특정 티커의 Thesis Map을 가져옵니다."""
    conn = get_connection()
    cursor = conn.cursor()
    result = {}
    try:
        cursor.execute("""
            SELECT ticker, name, investment_thesis, key_indicators, catalysts, risks, 
                   kill_condition, noise_rules, earnings_checkpoints, valuation_criteria, one_line_conclusion, created_at, updated_at
            FROM thesis_maps
            WHERE ticker = ?
        """, (ticker.upper(),))
        row = cursor.fetchone()
        if row:
            keys = ["ticker", "name", "investment_thesis", "key_indicators", "catalysts", "risks", 
                    "kill_condition", "noise_rules", "earnings_checkpoints", "valuation_criteria", "one_line_conclusion", "created_at", "updated_at"]
            result = dict(zip(keys, row))
    except Exception as e:
        print(f"⚠️ [learning/db.py] get_thesis_map 실패: {e}")
    finally:
        conn.close()
    return result

def get_all_thesis_maps() -> list:
    """현재 감시 중인 모든 Thesis Map 목록을 조회합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    results = []
    try:
        cursor.execute("""
            SELECT ticker, name, investment_thesis, key_indicators, catalysts, risks, 
                   kill_condition, noise_rules, earnings_checkpoints, valuation_criteria, one_line_conclusion, created_at, updated_at
            FROM thesis_maps
            ORDER BY ticker ASC
        """)
        rows = cursor.fetchall()
        keys = ["ticker", "name", "investment_thesis", "key_indicators", "catalysts", "risks", 
                "kill_condition", "noise_rules", "earnings_checkpoints", "valuation_criteria", "one_line_conclusion", "created_at", "updated_at"]
        for row in rows:
            results.append(dict(zip(keys, row)))
    except Exception as e:
        print(f"⚠️ [learning/db.py] get_all_thesis_maps 실패: {e}")
    finally:
        conn.close()
    return results

def delete_thesis_map(ticker: str) -> bool:
    """특정 종목의 Thesis Map을 삭제합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    success = False
    try:
        cursor.execute("DELETE FROM thesis_maps WHERE ticker = ?", (ticker.upper(),))
        conn.commit()
        # 영향을 받은 행의 수 확인
        if cursor.rowcount > 0:
            success = True
    except Exception as e:
        print(f"⚠️ [learning/db.py] delete_thesis_map 실패: {e}")
    finally:
        conn.close()
    return success

def add_graph_edge(source_type: str, source_id: str, target_type: str, target_id: str, relation_type: str, weight: float = 1.0) -> bool:
    """지식 그래프에 노드 간의 엣지(관계)를 추가하거나 업데이트합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    success = False
    try:
        # 동일한 소스-타겟-관계가 존재하면 weight와 생성일을 업데이트
        cursor.execute("""
            INSERT INTO knowledge_graph (source_type, source_id, target_type, target_id, relation_type, weight)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (source_type, source_id, target_type, target_id, relation_type, weight))
        conn.commit()
        success = True
    except Exception as e:
        print(f"⚠️ [learning/db.py] add_graph_edge 실패: {e}")
    finally:
        conn.close()
    return success

def get_related_nodes(node_type: str, node_id: str) -> list:
    """특정 노드와 연관된 다른 노드 리스트를 지식 그래프에서 조회합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    results = []
    try:
        # 단방향 및 역방향 관계 모두 조회
        cursor.execute("""
            SELECT target_type as node_type, target_id as node_id, relation_type, weight, 'outgoing' as direction
            FROM knowledge_graph
            WHERE source_type = ? AND source_id = ?
            UNION
            SELECT source_type as node_type, source_id as node_id, relation_type, weight, 'incoming' as direction
            FROM knowledge_graph
            WHERE target_type = ? AND target_id = ?
        """, (node_type, node_id, node_type, node_id))
        rows = cursor.fetchall()
        keys = ["node_type", "node_id", "relation_type", "weight", "direction"]
        for row in rows:
            results.append(dict(zip(keys, row)))
    except Exception as e:
        print(f"⚠️ [learning/db.py] get_related_nodes 실패: {e}")
    finally:
        conn.close()
    return results

def delete_graph_edges(source_type: str, source_id: str) -> bool:
    """특정 소스 노드로부터 나가는 모든 관계를 삭제합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    success = False
    try:
        cursor.execute("""
            DELETE FROM knowledge_graph 
            WHERE source_type = ? AND source_id = ?
        """, (source_type, source_id))
        conn.commit()
        success = True
    except Exception as e:
        print(f"⚠️ [learning/db.py] delete_graph_edges 실패: {e}")
    finally:
        conn.close()
    return success

# SQLite DB 초기화 자동 실행
init_db()
