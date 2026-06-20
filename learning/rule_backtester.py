# LLM 제안 규칙을 과거 decision_traces × outcomes 위에서 검증.
# 발동군 vs 미발동군 forward alpha 차이를 부트스트랩 신뢰구간으로 판정.
from __future__ import annotations
import os
import sys
import numpy as np
from typing import List, Dict, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from learning.db import get_connection
from learning.structured_rules import rule_matches, validate_rule_schema

MIN_MATCHED = 20
MIN_UNMATCHED = 20
HORIZON_DAYS = 20
CI = 0.95
N_BOOTSTRAP = 2000

def load_labeled_decisions(horizon: int = HORIZON_DAYS) -> List[Dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(reports)")
    has_deg = any(c[1] == "is_degraded" for c in cur.fetchall())
    deg = "AND COALESCE(r.is_degraded,0)=0" if has_deg else ""
    cur.execute(f"""
        SELECT d.pe,d.peg,d.inst_own,d.beta,d.sector,d.regime,d.vol_ratio,d.is_vol_surge,
               d.s_rising,d.m_rising,d.l_rising,d.signal_label,d.mtf_entry_grade,d.track,
               o.alpha_return_pct
        FROM decision_traces d
        JOIN reports r ON d.run_id=r.run_id AND d.ticker=r.ticker
        JOIN outcomes o ON o.report_id=r.id
        WHERE o.days_elapsed=? AND o.alpha_return_pct IS NOT NULL {deg}
    """, (horizon,))
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows

def _bootstrap_diff_ci(matched: np.ndarray, unmatched: np.ndarray) -> tuple[float, float]:
    rng = np.random.default_rng(42)
    diffs = np.empty(N_BOOTSTRAP)
    for i in range(N_BOOTSTRAP):
        diffs[i] = (rng.choice(matched, len(matched), True).mean()
                    - rng.choice(unmatched, len(unmatched), True).mean())
    return float(np.percentile(diffs, (1 - CI) / 2 * 100)), float(np.percentile(diffs, (1 + CI) / 2 * 100))

def backtest_rule(rule: dict, samples: Optional[List[Dict]] = None) -> dict:
    validate_rule_schema(rule)
    if samples is None:
        samples = load_labeled_decisions()
    matched = np.array([s["alpha_return_pct"] for s in samples if rule_matches(rule, s)], float)
    unmatched = np.array([s["alpha_return_pct"] for s in samples if not rule_matches(rule, s)], float)
    res = {
        "rule_id": rule.get("rule_id"),
        "action": rule.get("action"),
        "n_matched": len(matched),
        "n_unmatched": len(unmatched),
        "n_total": len(samples)
    }
    if len(matched) < MIN_MATCHED or len(unmatched) < MIN_UNMATCHED:
        res["verdict"] = "INSUFFICIENT_DATA"
        res["reason"] = f"표본 부족 (matched={len(matched)}, unmatched={len(unmatched)})"
        return res
    md, ud = float(matched.mean()), float(unmatched.mean())
    diff = md - ud
    lo, hi = _bootstrap_diff_ci(matched, unmatched)
    res.update({
        "matched_avg_alpha": round(md, 3),
        "unmatched_avg_alpha": round(ud, 3),
        "alpha_diff": round(diff, 3),
        "ci_low": round(lo, 3),
        "ci_high": round(hi, 3),
        "matched_win_rate": round(float((matched > 0).mean()) * 100, 1)
    })
    promote = (hi < 0) if rule.get("action") in ("veto", "penalize") else (lo > 0)
    res["verdict"] = "PROMOTE" if promote else "REJECT"
    res["reason"] = f"{rule.get('action')} / alpha차 {diff:+.2f}%p (95%CI [{lo:+.2f},{hi:+.2f}]) → {res['verdict']}"
    return res
