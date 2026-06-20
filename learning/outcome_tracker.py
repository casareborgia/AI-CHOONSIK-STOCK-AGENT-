# ==============================================================================
# [AI Trading Agent] 모듈 B: 정밀 성과 추적기 (learning/outcome_tracker.py)
# ==============================================================================
# 리포트 발행 후 5, 10, 20 영업일이 경과한 시점에 yfinance를 연동하여 실제 주가를 분석하고,
# 기간 내 최고/최저가를 추적하여 목표가/손절선 도달 및 최종 수익률을 DB에 정확히 기록합니다.

import sqlite3
import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd
import sys
import os

# 프로젝트 루트 디렉토리 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from learning.db import get_connection

CHECK_INTERVALS = [5, 10, 20]  # 추적 영업일 간격

def track_outcomes():
    """
    매일 1회 정기 실행: 과거 30일 이내에 발행되었으나 특정 영업일 성과가 
    아직 집계되지 않은 모든 리포트의 성과를 추적하여 DB에 반영합니다.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. 과거 40일 이내에 기록된 미완료 리포트 목록 조회
    # (영업일 기준 20일 추적을 완벽히 포함하기 위해 40일 범위 스캔)
    cursor.execute("""
        SELECT r.id, r.ticker, r.date, r.close_price, r.target_price, r.stop_loss_pct
        FROM reports r
        WHERE r.date >= date('now', '-40 days')
        ORDER BY r.date DESC
    """)
    reports = cursor.fetchall()
    
    if not reports:
        print("   📡 [outcome_tracker.py] 성과를 추적할 과거 리포트 대상이 없습니다.")
        conn.close()
        return
        
    print(f"   📡 [outcome_tracker.py] 총 {len(reports)}개의 과거 리포트에 대한 실시간 성과 추적 시작...")
    
    for report_id, ticker, report_date, entry_price, target_price, stop_pct in reports:
        # 이미 5, 10, 20일 기록이 모두 존재하는 리포트라면 패스
        cursor.execute("SELECT days_elapsed FROM outcomes WHERE report_id = ?", (report_id,))
        existing_intervals = [row[0] for row in cursor.fetchall()]
        
        if set(existing_intervals) == set(CHECK_INTERVALS):
            continue
            
        report_dt = datetime.strptime(report_date, "%Y-%m-%d")
        days_since = (datetime.now() - report_dt).days
        
        # 5영업일 이상 경과했을 때만 데이터 추적 시도
        if days_since < 5:
            continue
            
        # 2. 영업일 휴일/주말 예외를 100% 극복하기 위해, 리포트 발행일 이후 45일간의 주가 데이터를 한 번에 가져옴
        end_date = (report_dt + timedelta(days=45)).strftime("%Y-%m-%d")
        try:
            df = yf.download(ticker, start=report_date, end=end_date, progress=False)
            df_spy = yf.download("SPY", start=report_date, end=end_date, progress=False)
            if df.empty or len(df) < 2:
                continue
                
            # 다중 인덱스 제거 및 인덱스 정합성 확보
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if isinstance(df_spy.columns, pd.MultiIndex):
                df_spy.columns = df_spy.columns.get_level_values(0)
                
        except Exception as e:
            print(f"   ⚠️ [outcome_tracker.py] {ticker} 또는 SPY 주가 다운로드 실패: {e}")
            continue
            
        # 데이터프레임의 행 자체가 '영업일'을 의미하므로 날짜 오차를 원천적으로 완치함
        total_rows = len(df)
        
        for interval in CHECK_INTERVALS:
            if interval in existing_intervals:
                continue
                
            # 해당 영업일 행이 아직 도래하지 않은 경우
            if total_rows <= interval:
                continue
                
            # 정확한 추적 영업일 시점의 날짜 및 종가 확보
            check_date = df.index[interval].strftime("%Y-%m-%d")
            check_price = float(df["Close"].iloc[interval])
            
            # 기간 내(1일부터 interval영업일까지)의 최고/최저가 추출하여 체결 정확성 극대화
            period_high = float(df["High"].iloc[1:interval+1].max())
            period_low = float(df["Low"].iloc[1:interval+1].min())
            
            # 3. 목표가 및 손절선 도달 체크
            hit_target = False
            if target_price and target_price > 0:
                # 기간 내 최고가가 목표가 이상 터치한 적이 있는가
                hit_target = period_high >= target_price
                
            hit_stoploss = False
            if stop_pct and stop_pct > 0:
                # 기간 내 최저가가 손절가 이하로 추락한 적이 있는가
                stop_price = entry_price * (1 - abs(stop_pct)/100)
                hit_stoploss = period_low <= stop_price
                
            # 4. 수익률 및 벤치마크(Alpha) 연산
            return_pct = ((check_price - entry_price) / entry_price) * 100
            
            # SPY 수익률 계산
            benchmark_return_pct = 0.0
            try:
                if not df_spy.empty and len(df_spy) > interval:
                    spy_entry = float(df_spy["Close"].iloc[0])
                    spy_check = float(df_spy["Close"].iloc[interval])
                    benchmark_return_pct = ((spy_check - spy_entry) / spy_entry) * 100
            except Exception as e:
                print(f"   ⚠️ [outcome_tracker.py] SPY 수익률 연산 실패: {e}")
                
            alpha_return_pct = return_pct - benchmark_return_pct
            
            # 5. 최종 성과 라벨 판정 (Alpha가 양수이고 컷오프 안당했으면 win)
            # 승/패 판정을 절대수익(return_pct)이 아니라 alpha 기준으로 판정
            if hit_stoploss:
                outcome = "stopped_out"
            elif alpha_return_pct > 0:
                outcome = "win"
            else:
                outcome = "loss"
                
            # 6. outcomes DB 테이블 기록 삽입
            cursor.execute("""
                INSERT INTO outcomes (report_id, ticker, entry_price, check_date, check_price, days_elapsed, return_pct, hit_target, hit_stoploss, outcome, benchmark_return_pct, alpha_return_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (report_id, ticker, entry_price, check_date, check_price, interval, round(return_pct, 2), int(hit_target), int(hit_stoploss), outcome, round(benchmark_return_pct, 2), round(alpha_return_pct, 2)))
            
            print(f"   📊 [성과 기록] {ticker} ({interval}일 경과) | 수익률: {return_pct:+.2f}% (Alpha: {alpha_return_pct:+.2f}%) | 결과: {outcome} ({check_date} 기준)")
            
    conn.commit()
    conn.close()
    print("   ✅ [outcome_tracker.py] 과거 리포트 성과 추적 및 DB 동기화 완료.")
