# 규칙을 자연어가 아니라 decision_traces 피처에 대한 평가 가능한 조건식으로 표현.
from __future__ import annotations
from typing import Any, Dict, List

ALLOWED_FEATURES = {
    "pe", "peg", "inst_own", "beta", "sector", "regime",
    "ma5", "ma20", "ma60", "ma120",
    "stoch_s_k", "stoch_s_d", "stoch_m_k", "stoch_m_d", "stoch_l_k", "stoch_l_d",
    "s_rising", "m_rising", "l_rising",
    "vol_ratio", "is_vol_surge", "close", "signal_label", "mtf_entry_grade", "track",
}
_OPS = {
    "gt": lambda a, b: a is not None and a > b,
    "gte": lambda a, b: a is not None and a >= b,
    "lt": lambda a, b: a is not None and a < b,
    "lte": lambda a, b: a is not None and a <= b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "in": lambda a, b: a in b,
    "contains": lambda a, b: a is not None and str(b).lower() in str(a).lower(),
}

class RuleValidationError(ValueError): pass

def validate_rule_schema(rule: dict) -> None:
    if not isinstance(rule, dict): raise RuleValidationError("규칙은 dict")
    if not rule.get("rule_id"): raise RuleValidationError("rule_id 누락")
    clauses = rule.get("when")
    if not isinstance(clauses, list) or not clauses:
        raise RuleValidationError("when 절이 비어 있음")
    for c in clauses:
        if c.get("feature") not in ALLOWED_FEATURES:
            raise RuleValidationError(f"허용 안 된 피처: {c.get('feature')}")
        if c.get("op") not in _OPS:
            raise RuleValidationError(f"허용 안 된 연산자: {c.get('op')}")
        if "value" not in c: raise RuleValidationError(f"value 누락: {c}")
    if rule.get("action") not in ("veto", "penalize", "boost"):
        raise RuleValidationError("action은 veto|penalize|boost")

def rule_matches(rule: dict, row: dict) -> bool:
    for c in rule["when"]:
        try:
            if not _OPS[c["op"]](row.get(c["feature"]), c["value"]):
                return False
        except TypeError:
            return False
    return True
