from dataclasses import dataclass
import re
from typing import Literal

from src.config import TIER1_MODEL, TIER2_MODEL

TierLevel = Literal["tier1", "tier2"]


@dataclass(frozen=True)
class TierDecision:
    """Represents the selected LLM tier, concrete model ID, and escalation rationale."""

    tier: TierLevel
    model: str
    escalated: bool = False
    reason: str = ""


_QUANT_DEMANDING_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bcagr\b", "multi_year_cagr_derivation"),
    (r"\b(3|4|5)[\s-]*year\b", "multi_year_trend_modeling"),
    (r"\bmulti[\s-]*year\b", "multi_year_trend_modeling"),
    (
        r"\b(roic|return on invested capital|dupont|wacc|dcf|working capital|interest coverage|debt[\s-]to[\s-]equity)\b",
        "advanced_capital_or_ratio_modeling",
    ),
    (
        r"\b(margin (expansion|compression|bridge|decomposition)|segment mix|waterfall|fcf yield|justified by)\b",
        "margin_or_valuation_decomposition",
    ),
)

_QUAL_DEMANDING_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        r"\b(restatement|material weakness|goodwill impairment|contingent liabilit\w*|off[\s-]balance)\b",
        "forensic_accounting_disclosure_audit",
    ),
    (
        r"\b(contradict\w*|reconcil\w*|diverg\w*|discrepanc\w*|red flag\w*|tone shift|forensic|insider\w*.*guidance)\b",
        "cross_source_contradiction_synthesis",
    ),
    (
        r"\b(antitrust|doj|department of justice|eu dma|patent infringement|tax valuation allowance)\b",
        "complex_regulatory_or_legal_analysis",
    ),
)

_GENERAL_DEMANDING_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        r"\b(deep[\s-]*dive|forensic|institutional memo|investment thesis|bull (vs\.?|and) bear)\b",
        "deep_dive_institutional_research",
    ),
    (
        r"\b(contradict\w*|reconcil\w*|diverg\w*|discrepanc\w*)\b",
        "cross_domain_reconciliation",
    ),
)


def _infer_tier_for_explicit_model(model_name: str) -> TierLevel:
    lowered = model_name.lower()
    if "terra" in lowered or model_name == TIER1_MODEL:
        return "tier1"
    return "tier2"


def assess_demanding_task(
    question: str,
    tickers: list[str] | None = None,
    role: str | None = None,
) -> tuple[bool, str]:
    """
    Evaluates whether a specialist sub-task or single-agent query warrants proactive
    escalation from Tier 2 (gpt-6-luna) to Tier 1 (gpt-6.1-terra).
    """
    q_lower = question.lower()
    active_tickers = [t for t in (tickers or []) if t]

    # 3+ concurrent peer tickers create denser comparative context
    if len(active_tickers) >= 3 and role in (None, "unified", "quant", "qual"):
        return True, "multi_peer_cohort_analysis"

    # 3+ distinct fiscal years referenced in the prompt (e.g., 2022, 2023, 2024, 2025)
    distinct_years = set(re.findall(r"\b202[0-9]\b", q_lower))
    if len(distinct_years) >= 3 and role in (None, "unified", "quant"):
        return True, "multi_period_time_series_analysis"

    if role in ("quant", None, "unified"):
        for pattern, reason in _QUANT_DEMANDING_PATTERNS:
            if re.search(pattern, q_lower):
                return True, reason

    if role in ("qual", None, "unified"):
        for pattern, reason in _QUAL_DEMANDING_PATTERNS:
            if re.search(pattern, q_lower):
                return True, reason

    for pattern, reason in _GENERAL_DEMANDING_PATTERNS:
        if re.search(pattern, q_lower):
            return True, reason

    # Long, multi-clause analytical prompts (> 45 words) in unified single-agent mode
    if role in (None, "unified") and len(q_lower.split()) >= 45:
        return True, "high_complexity_multi_clause_query"

    return False, ""


def resolve_supervisor_tier(explicit_model: str | None = None) -> TierDecision:
    """
    Lead Multi-Agent Supervisor & Final Executive Synthesizer always defaults to
    Tier 1 (gpt-6.1-terra) unless an explicit model override is supplied.
    """
    if explicit_model:
        return TierDecision(
            tier=_infer_tier_for_explicit_model(explicit_model),
            model=explicit_model,
            escalated=False,
            reason="explicit_model_override",
        )
    return TierDecision(
        tier="tier1",
        model=TIER1_MODEL,
        escalated=False,
        reason="tier1_lead_supervisor",
    )


def resolve_subagent_tier(
    question: str,
    role: str,
    tickers: list[str] | None = None,
    explicit_model: str | None = None,
    sole_specialist: bool = False,
) -> TierDecision:
    """
    Specialist sub-agents (quant, qual, sentiment) default to fast Tier 2 (gpt-6-luna),
    escalating to Tier 1 (gpt-6.1-terra) for demanding analytical tasks or when a
    multi-agent query dispatches a single specialist directly without a separate synthesis pass.
    """
    if explicit_model:
        return TierDecision(
            tier=_infer_tier_for_explicit_model(explicit_model),
            model=explicit_model,
            escalated=False,
            reason="explicit_model_override",
        )

    is_demanding, reason = assess_demanding_task(
        question=question, tickers=tickers, role=role
    )
    if is_demanding:
        return TierDecision(
            tier="tier1",
            model=TIER1_MODEL,
            escalated=True,
            reason=reason,
        )

    if sole_specialist:
        return TierDecision(
            tier="tier1",
            model=TIER1_MODEL,
            escalated=True,
            reason="sole_specialist_direct_tier1_synthesis",
        )

    return TierDecision(
        tier="tier2",
        model=TIER2_MODEL,
        escalated=False,
        reason="routine_specialist_workhorse",
    )


def resolve_single_agent_tier(
    question: str,
    ticker: str,
    explicit_model: str | None = None,
) -> TierDecision:
    """
    Single-agent queries run on Tier 2 (gpt-6-luna) for fast factual lookups and
    escalate to Tier 1 (gpt-6.1-terra) for demanding multi-period or forensic queries.
    """
    if explicit_model:
        return TierDecision(
            tier=_infer_tier_for_explicit_model(explicit_model),
            model=explicit_model,
            escalated=False,
            reason="explicit_model_override",
        )

    is_demanding, reason = assess_demanding_task(
        question=question, tickers=[ticker], role="unified"
    )
    if is_demanding:
        return TierDecision(
            tier="tier1",
            model=TIER1_MODEL,
            escalated=True,
            reason=reason,
        )

    return TierDecision(
        tier="tier2",
        model=TIER2_MODEL,
        escalated=False,
        reason="routine_single_agent_lookup",
    )


def escalate_on_guard_failure(
    current_decision: TierDecision,
    explicit_model: str | None = None,
) -> TierDecision:
    """
    Reactively escalates a Tier 2 (gpt-6-luna) agent to Tier 1 (gpt-6.1-terra)
    if Citation Guard verification fails during self-correction.
    """
    if explicit_model or current_decision.model == TIER1_MODEL:
        return current_decision
    return TierDecision(
        tier="tier1",
        model=TIER1_MODEL,
        escalated=True,
        reason="citation_guard_retry_escalation",
    )
