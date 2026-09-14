"""
Declarative YAML policy evaluation — the fourth seam (Section 4). Policy is
data, loaded at runtime: adding or changing a rule means editing a YAML
file under mediator/policy/policies/, never this module. First rule whose
`when` clause matches wins.
"""

from __future__ import annotations

import operator as op
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from common.schema import FailMode, PolicyDecision

_OPERATORS: dict[str, Any] = {
    "eq": op.eq,
    "ne": op.ne,
    "gt": op.gt,
    "gte": op.ge,
    "lt": op.lt,
    "lte": op.le,
    "endswith": lambda a, b: str(a).lower().endswith(str(b).lower()),
    "not_endswith": lambda a, b: not str(a).lower().endswith(str(b).lower()),
    "contains": lambda a, b: str(b).lower() in str(a).lower(),
}

DEFAULT_POLICY_PATH = Path(__file__).parent / "policies" / "default.yaml"


@dataclass
class PolicyEvaluation:
    decision: PolicyDecision
    policy_id: str
    rule_matched: str
    reason: str
    fail_mode: FailMode


@dataclass
class _Rule:
    name: str
    when: dict[str, Any]
    decision: PolicyDecision
    fail_mode: FailMode
    reason: str


class PolicyEngine:
    def __init__(self, policy_id: str, rules: list[_Rule]) -> None:
        self.policy_id = policy_id
        self._rules = rules

    @classmethod
    def load(cls, path: Path | str = DEFAULT_POLICY_PATH) -> "PolicyEngine":
        raw = yaml.safe_load(Path(path).read_text())
        rules = [
            _Rule(
                name=r["name"],
                when=r.get("when", {}),
                decision=PolicyDecision(r["decision"]),
                fail_mode=FailMode(r["fail_mode"]),
                reason=r["reason"],
            )
            for r in raw["rules"]
        ]
        return cls(policy_id=raw["policy_id"], rules=rules)

    def evaluate(
        self, *, tool_name: str, arguments: dict[str, Any], risk: str, in_catalogue: bool
    ) -> PolicyEvaluation:
        for rule in self._rules:
            if self._matches(rule.when, tool_name, arguments, risk, in_catalogue):
                return PolicyEvaluation(
                    decision=rule.decision,
                    policy_id=self.policy_id,
                    rule_matched=rule.name,
                    reason=rule.reason,
                    fail_mode=rule.fail_mode,
                )
        # I10: failure behaviour is policy, not a blanket default. But an
        # authoring gap (no rule matched at all) is not a tool-class
        # decision Blackbox gets to make per-call — the safe direction for
        # an incomplete policy file is to deny and say so loudly, not to
        # silently fall through to allow.
        return PolicyEvaluation(
            decision=PolicyDecision.deny,
            policy_id=self.policy_id,
            rule_matched="_no_rule_matched",
            reason=f"no policy rule matched tool={tool_name!r}; policy file is incomplete",
            fail_mode=FailMode.fail_closed,
        )

    def _matches(
        self, when: dict[str, Any], tool_name: str, arguments: dict[str, Any], risk: str, in_catalogue: bool
    ) -> bool:
        if "tool_not_in_catalogue" in when and when["tool_not_in_catalogue"] != (not in_catalogue):
            return False
        if "tool" in when and when["tool"] != tool_name:
            return False
        if "risk_in" in when and risk not in when["risk_in"]:
            return False
        if "argument" in when:
            if when["argument"] not in arguments:
                return False
            arg_value = arguments[when["argument"]]
            operator_fn = _OPERATORS[when["operator"]]
            if not operator_fn(arg_value, when["value"]):
                return False
        return True
