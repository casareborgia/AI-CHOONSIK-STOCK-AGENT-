import unittest
from learning.structured_rules import validate_rule_schema, RuleValidationError, rule_matches
from learning.rule_backtester import backtest_rule


class TestRuleBacktester(unittest.TestCase):

    def setUp(self):
        # 1. 테스트용 합성 의사결정 추적 샘플군 (pe, close, alpha_return_pct 등을 포함)
        self.samples = []
        
        # pe > 30 조건에 대해 우수한 성과를 보인 샘플 25개
        for i in range(25):
            self.samples.append({
                "pe": 35.0 + i,
                "peg": 1.1,
                "inst_own": 80.0,
                "beta": 1.2,
                "sector": "Technology",
                "regime": "aligned",
                "vol_ratio": 1.5,
                "close": 150.0,
                "signal_label": "매수",
                "alpha_return_pct": 5.0  # 발동군은 높은 초과수익률
            })
            
        # pe <= 30 조건(pe > 30을 만족하지 않음)에 대해 낮은 성과를 보인 샘플 25개
        for i in range(25):
            self.samples.append({
                "pe": 10.0 + i * 0.5,
                "peg": 0.8,
                "inst_own": 50.0,
                "beta": 0.9,
                "sector": "Healthcare",
                "regime": "mixed",
                "vol_ratio": 1.0,
                "close": 80.0,
                "signal_label": "관망",
                "alpha_return_pct": -2.0  # 미발동군은 낮은 초과수익률
            })

    def test_rule_validation(self):
        # 허용된 정상 규칙 검증
        valid_rule = {
            "rule_id": "R101",
            "when": [
                {"feature": "pe", "op": "gt", "value": 30.0}
            ],
            "action": "boost"
        }
        try:
            validate_rule_schema(valid_rule)
        except RuleValidationError:
            self.fail("정상 규칙에 대해 예외가 발생했습니다.")

        # 비정상 규칙 (허용되지 않은 피처)
        invalid_feature_rule = {
            "rule_id": "R102",
            "when": [
                {"feature": "invalid_feature_name", "op": "gt", "value": 10.0}
            ],
            "action": "boost"
        }
        with self.assertRaises(RuleValidationError):
            validate_rule_schema(invalid_feature_rule)

        # 비정상 규칙 (허용되지 않은 액션)
        invalid_action_rule = {
            "rule_id": "R103",
            "when": [
                {"feature": "pe", "op": "gt", "value": 30.0}
            ],
            "action": "invalid_action_name"
        }
        with self.assertRaises(RuleValidationError):
            validate_rule_schema(invalid_action_rule)

    def test_rule_matches(self):
        rule = {
            "rule_id": "R101",
            "when": [
                {"feature": "pe", "op": "gt", "value": 30.0},
                {"feature": "signal_label", "op": "eq", "value": "매수"}
            ],
            "action": "boost"
        }
        row_match = {"pe": 35.0, "signal_label": "매수"}
        row_fail = {"pe": 25.0, "signal_label": "매수"}
        row_fail2 = {"pe": 35.0, "signal_label": "관망"}
        
        self.assertTrue(rule_matches(rule, row_match))
        self.assertFalse(rule_matches(rule, row_fail))
        self.assertFalse(rule_matches(rule, row_fail2))

    def test_backtest_rule_promote(self):
        # 발동군의 초과수익률 평균(5.0)이 미발동군(-2.0)보다 유의미하게 우수하므로 boost 액션 시 PROMOTE 판정이 나와야 함
        rule = {
            "rule_id": "R101",
            "when": [
                {"feature": "pe", "op": "gt", "value": 30.0}
            ],
            "action": "boost"
        }
        res = backtest_rule(rule, samples=self.samples)
        self.assertEqual(res["verdict"], "PROMOTE")
        self.assertTrue(res["alpha_diff"] > 0)

    def test_backtest_rule_reject(self):
        # 효과가 전혀 없는 무의미한 규칙 (모든 샘플에 대해 성과 차이가 무작위인 경우)
        for s in self.samples:
            s["alpha_return_pct"] = 1.0  # 모든 샘플의 초과수익률을 동일하게 고정
            
        rule = {
            "rule_id": "R101",
            "when": [
                {"feature": "pe", "op": "gt", "value": 30.0}
            ],
            "action": "boost"
        }
        res = backtest_rule(rule, samples=self.samples)
        self.assertEqual(res["verdict"], "REJECT")

    def test_backtest_rule_insufficient_data(self):
        # 표본 수가 부족한 경우 (검출 샘플이 5개에 불과)
        small_samples = self.samples[:10]  # 총 10개만 전달 (MIN_MATCHED=20 미만)
        rule = {
            "rule_id": "R101",
            "when": [
                {"feature": "pe", "op": "gt", "value": 30.0}
            ],
            "action": "boost"
        }
        res = backtest_rule(rule, samples=small_samples)
        self.assertEqual(res["verdict"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
