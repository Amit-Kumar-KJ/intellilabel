"""Phase 7.3: rule engine. Every rule is a small class; one family per file. Rules decide pass/fail;
the LLM never does."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Finding:
    rule_id: str
    severity: str  # critical | major | minor
    message: str
    element: str | None = None
    evidence_bbox: list | None = None
    requirement_id: str | None = None
    clause_ref: str | None = None
    requirement_text: str | None = None
    suggested_fix: str | None = None
    uncertain: bool = False
    evidence_text: str | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}


class Rule:
    id: str = ""
    family: str = ""
    severity: str = "major"
    title: str = ""

    def applies(self, ctx) -> bool:
        return bool(ctx["requirements_by_rule"].get(self.id))

    def reqs(self, ctx):
        return ctx["requirements_by_rule"].get(self.id, [])

    def finding(self, ctx, message, element=None, bbox=None, fix=None, severity=None, req=None, uncertain=False,
                evidence_text=None, **extra):
        req = req or (self.reqs(ctx)[0] if self.reqs(ctx) else None)
        return Finding(rule_id=self.id, severity=severity or self.severity, message=message, element=element,
                       evidence_bbox=bbox, requirement_id=req["requirement_id"] if req else None,
                       clause_ref=f"{req['regulation']} {req['section']}" if req else None,
                       requirement_text=req["requirement_text"] if req else None, suggested_fix=fix,
                       uncertain=uncertain, evidence_text=evidence_text, extra=extra)

    def check(self, model, ctx) -> list[Finding]:  # pragma: no cover - interface
        raise NotImplementedError


RULES: dict[str, Rule] = {}


def register(cls):
    RULES[cls.id] = cls()
    return cls


# import rule families so they self-register
from engines.rules import content, format, language, layout, presence, symbol, udi, version  # noqa: E402,F401
