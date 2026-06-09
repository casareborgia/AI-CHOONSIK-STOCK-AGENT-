# ==============================================================================
# [골든 회귀 테스트] core/technical_engine.evaluate_signal
# ==============================================================================
# 파동에너지 시그널 판정 로직이 코드 변경 후에도 동일하게 동작하는지 고정합니다.
# 네트워크(yfinance) 호출이 전혀 없으므로 결정적(deterministic)으로 항상 같은 결과를 냅니다.
#
# 실행:  pytest -q tests/test_technical_engine.py
#   또는: python -m pytest tests/test_technical_engine.py

import os
import sys
import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.technical_engine import evaluate_signal


def _make_aligned_uptrend(n: int = 200, vol_last: float = 2_500_000.0) -> pd.DataFrame:
    """완만한 상승 + 마지막 30봉 볼록(가속) 상승 → 정배열 & 3중 파동 상승 유도 (난수 없음)."""
    x = np.arange(n, dtype=float)
    close = 100.0 + 0.15 * x
    tail = np.arange(30, dtype=float)
    close[-30:] = close[-31] + 0.04 * tail ** 2
    high = close + 0.5
    low = close - 0.5
    vol = np.full(n, 1_000_000.0)
    vol[-1] = vol_last
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"Open": close, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )


ITEM = {"ticker": "TEST", "name": "Fixture Co", "sector": "Technology", "track": "Track A"}


def test_strong_buy_signal_is_stable():
    """정배열 + 3중 파동 상승 + 거래량 급증 → '강력매수' 시그널이 고정되어야 한다."""
    r = evaluate_signal(_make_aligned_uptrend(vol_last=2_500_000.0), ITEM, "Track A")
    assert r is not None
    assert r["regime"] == "aligned"
    assert r["signal"] == "🔥 정배열 추세지속 (강력매수)"
    assert (r["s_rising"], r["m_rising"], r["l_rising"]) == (True, True, True)
    assert r["is_vol_surge"] is True
    # 정배열 국면 거래량 허들 = VOL_MULTIPLIER * 0.8 = 1.2 * 0.8 = 0.96
    assert abs(r["vol_multiplier"] - 0.96) < 1e-6
    assert r["ma5"] > r["ma20"] > r["ma60"] > r["ma120"]


def test_low_volume_downgrades_signal():
    """동일 추세라도 거래량이 허들 미달이면 '강력매수'가 아닌 '분할매수'로 강등되어야 한다."""
    r = evaluate_signal(_make_aligned_uptrend(vol_last=300_000.0), ITEM, "Track A")
    assert r is not None
    assert r["is_vol_surge"] is False
    assert r["signal"] == "📈 정배열 파동정배열 (분할매수)"


def test_insufficient_data_returns_none():
    """40봉 미만 데이터는 분석에서 제외(None)되어야 한다."""
    df = _make_aligned_uptrend()
    assert evaluate_signal(df.iloc[:30], ITEM, "Track A") is None
    assert evaluate_signal(pd.DataFrame(), ITEM, "Track A") is None


def test_decision_trace_fields_present_and_typed():
    """decision_traces 적재에 필요한 모든 근거값이 result_item에 존재하고 타입이 올바른지 검증."""
    r = evaluate_signal(_make_aligned_uptrend(), ITEM, "Track A")
    float_fields = [
        "close", "high", "low", "vol_ratio", "vol_multiplier",
        "ma5", "ma20", "ma60", "ma120",
        "stoch_s_k", "stoch_s_d", "stoch_m_k", "stoch_m_d", "stoch_l_k", "stoch_l_d",
    ]
    for f in float_fields:
        assert f in r, f"누락된 근거 필드: {f}"
        assert isinstance(r[f], float), f"{f}는 float여야 함 (실제: {type(r[f])})"
    for f in ["s_rising", "m_rising", "l_rising", "is_vol_surge"]:
        assert isinstance(r[f], bool), f"{f}는 bool여야 함"
    assert r["regime"] in {"aligned", "reversed", "converged", "mixed"}
    # 기존 메타데이터 보존 확인
    assert r["ticker"] == "TEST"
    assert r["track"] == "Track A"


if __name__ == "__main__":
    # pytest 없이도 단독 실행 가능
    test_strong_buy_signal_is_stable()
    test_low_volume_downgrades_signal()
    test_insufficient_data_returns_none()
    test_decision_trace_fields_present_and_typed()
    print("✅ 모든 골든 테스트 통과")
