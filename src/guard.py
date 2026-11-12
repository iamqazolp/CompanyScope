import re
from typing import Any

from rapidfuzz import fuzz


def _normalize_text(text: str) -> str:
    """Normalizes whitespace, quotes, and punctuation for reliable substring matching."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _normalize_concept(concept: str | None) -> str:
    if not concept:
        return ""
    c = re.sub(r"[^a-z0-9]+", "", concept.lower())
    aliases = {
        "revenue": "revenues",
        "totalrevenue": "revenues",
        "totalrevenues": "revenues",
        "netincome": "netincomeloss",
        "operatingincome": "operatingincomeloss",
        "totalassets": "assets",
        "totalliabilities": "liabilities",
        "shareholdersequity": "stockholdersequity",
        "price": "spotprice",
        "stockprice": "spotprice",
        "shareprice": "spotprice",
        "currentprice": "spotprice",
        "pe": "trailingpe",
        "peratio": "trailingpe",
        "fwdpe": "forwardpe",
        "forwardperatio": "forwardpe",
        "evebitda": "evtoebitda",
        "enterprisetoeebitda": "evtoebitda",
        "targetprice": "analysttargetprice",
        "pricetarget": "analysttargetprice",
        "52weekhigh": "fiftytwoweekhigh",
        "52weeklow": "fiftytwoweeklow",
    }
    return aliases.get(c, c)


def _value_appears_in_answer(val: Any, clean_answer_digits: str) -> bool:
    if val is None:
        return False
    val_str = str(val).replace(".", "").replace("-", "").lstrip("0")
    if (val_str[:3] and val_str[:3] in clean_answer_digits) or (
        val_str[:2] and val_str[:2] in clean_answer_digits
    ):
        return True
    if isinstance(val, (int, float)):
        fval = abs(float(val))
        candidates = [
            f"{fval:.2f}",
            f"{fval:.1f}",
            f"{fval / 1e12:.2f}",
            f"{fval / 1e9:.2f}",
            f"{fval / 1e6:.1f}",
        ]
        for cand in candidates:
            cd = cand.replace(".", "").lstrip("0")
            if len(cd) >= 2 and cd[:2] in clean_answer_digits:
                return True
    return False


def check_citations(
    output: dict[str, Any], tool_results: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Inspects all citations in `output` against `tool_results` and returns
    (valid_citations, invalid_citations).
    """
    if not isinstance(output, dict) or "citations" not in output:
        return [], []

    valid_citations: list[dict[str, Any]] = []
    invalid_citations: list[dict[str, Any]] = []
    answer = str(output.get("answer", ""))
    clean_answer_digits = answer.replace(".", "").replace(",", "")

    has_calculator_result = any(
        isinstance(v, (int, float)) for v in tool_results.values()
    )

    for citation in output.get("citations", []):
        if not isinstance(citation, dict):
            continue
        cit_type = citation.get("type")
        is_valid = False

        if cit_type in ("narrative", "earnings", "sentiment", "insider"):
            quote = str(citation.get("quote", "")).strip()
            if not quote:
                invalid_citations.append(
                    {"citation": citation, "reason": f"Empty quote in {cit_type} citation."}
                )
                continue

            norm_quote = _normalize_text(quote)

            for res_data in tool_results.values():
                if isinstance(res_data, list):
                    for item in res_data:
                        if isinstance(item, dict) and "chunk_text" in item:
                            norm_chunk = _normalize_text(str(item["chunk_text"]))
                            if norm_quote in norm_chunk:
                                is_valid = True
                                break
                            if (
                                len(norm_quote) >= 15
                                and fuzz.partial_ratio(norm_quote, norm_chunk) >= 88.0
                            ):
                                is_valid = True
                                break
                if is_valid:
                    break

            if not is_valid:
                invalid_citations.append(
                    {
                        "citation": citation,
                        "reason": "Quote was not found verbatim in retrieved filing chunks.",
                    }
                )

        elif cit_type in ("numeric", "market"):
            concept = _normalize_concept(citation.get("concept"))
            year = str(citation.get("year", "")).strip()
            cit_ticker = str(citation.get("ticker", "")).upper().strip()

            for res_data in tool_results.values():
                if not isinstance(res_data, dict):
                    continue
                res_ticker = str(res_data.get("ticker", "")).upper().strip()
                ticker_matches = (
                    not cit_ticker or not res_ticker or cit_ticker == res_ticker
                )

                # 1. Standard SEC XBRL get_financial_data result
                if "value" in res_data and cit_type == "numeric":
                    res_concept = _normalize_concept(res_data.get("concept"))
                    res_period = str(res_data.get("period", "")).strip()
                    concept_matches = (
                        not concept
                        or res_concept == concept
                        or concept in res_concept
                        or res_concept in concept
                    )
                    year_matches = (
                        res_period == year
                        or year.lower() in ("latest", "current", "recent", "")
                    )
                    if ticker_matches and concept_matches and year_matches:
                        if (
                            _value_appears_in_answer(
                                res_data.get("value"), clean_answer_digits
                            )
                            or has_calculator_result
                        ):
                            is_valid = True
                        break

                # 2. Live market quote & valuation multiples (get_live_market_data)
                if isinstance(res_data.get("metrics"), dict) and ticker_matches:
                    metrics_map = res_data["metrics"]
                    for m_key, m_info in metrics_map.items():
                        norm_mk = _normalize_concept(m_key)
                        if (
                            concept
                            and (
                                norm_mk == concept
                                or concept in norm_mk
                                or norm_mk in concept
                            )
                            and isinstance(m_info, dict)
                        ):
                            if (
                                _value_appears_in_answer(
                                    m_info.get("value"), clean_answer_digits
                                )
                                or has_calculator_result
                            ):
                                is_valid = True
                            break
                if is_valid:
                    break

            if not is_valid:
                invalid_citations.append(
                    {
                        "citation": citation,
                        "reason": "Numeric/market metric was not fetched via tools or digits do not match.",
                    }
                )
        else:
            invalid_citations.append(
                {"citation": citation, "reason": f"Unknown citation type '{cit_type}'."}
            )

        if is_valid:
            valid_citations.append(citation)

    return valid_citations, invalid_citations


def _enrich_citation(
    citation: dict[str, Any], tool_results: dict[str, Any]
) -> dict[str, Any]:
    """Attaches source_context / XBRL metadata onto a verified citation for UI inspection."""
    enriched = dict(citation)
    cit_type = enriched.get("type")

    if cit_type in ("narrative", "earnings", "sentiment", "insider"):
        quote = str(enriched.get("quote", "")).strip()
        norm_quote = _normalize_text(quote)
        target_cid = str(enriched.get("chunk_id", "")).strip()

        best_item: dict[str, Any] | None = None
        for res_data in tool_results.values():
            if isinstance(res_data, list):
                for item in res_data:
                    if not isinstance(item, dict) or "chunk_text" not in item:
                        continue
                    if target_cid and str(item.get("chunk_id", "")) == target_cid:
                        best_item = item
                        break
                    norm_chunk = _normalize_text(str(item["chunk_text"]))
                    if norm_quote and (
                        norm_quote in norm_chunk
                        or (
                            len(norm_quote) >= 15
                            and fuzz.partial_ratio(norm_quote, norm_chunk) >= 88.0
                        )
                    ):
                        best_item = item
            if best_item and target_cid and str(best_item.get("chunk_id", "")) == target_cid:
                break

        if best_item:
            enriched.setdefault("source_context", str(best_item.get("chunk_text", "")))
            if best_item.get("url"):
                enriched.setdefault("source_url", str(best_item["url"]))

    elif cit_type in ("numeric", "market"):
        concept = _normalize_concept(enriched.get("concept"))
        year = str(enriched.get("year", "")).strip()
        cit_ticker = str(enriched.get("ticker", "")).upper().strip()
        for res_data in tool_results.values():
            if not isinstance(res_data, dict):
                continue
            res_ticker = str(res_data.get("ticker", "")).upper().strip()
            ticker_ok = not cit_ticker or not res_ticker or cit_ticker == res_ticker

            if "value" in res_data and cit_type == "numeric":
                res_concept = _normalize_concept(res_data.get("concept"))
                res_period = str(res_data.get("period", "")).strip()
                concept_ok = (
                    not concept
                    or res_concept == concept
                    or concept in res_concept
                    or res_concept in concept
                )
                year_ok = (
                    res_period == year
                    or year.lower() in ("latest", "current", "recent", "")
                )
                if ticker_ok and concept_ok and year_ok:
                    if res_period.isdigit() and year.lower() in (
                        "latest",
                        "current",
                        "recent",
                        "",
                    ):
                        enriched["year"] = int(res_period)
                    enriched.setdefault("verified_value", res_data.get("value"))
                    enriched.setdefault("unit", res_data.get("unit", "USD"))
                    if res_data.get("filing_date"):
                        enriched.setdefault("filing_date", res_data.get("filing_date"))
                    if res_data.get("form"):
                        enriched.setdefault("form", res_data.get("form"))
                    break

            if isinstance(res_data.get("metrics"), dict) and ticker_ok:
                matched_live = False
                for m_key, m_info in res_data["metrics"].items():
                    norm_mk = _normalize_concept(m_key)
                    if (
                        concept
                        and (
                            norm_mk == concept
                            or concept in norm_mk
                            or norm_mk in concept
                        )
                        and isinstance(m_info, dict)
                    ):
                        enriched["type"] = "market"
                        enriched["concept"] = m_key
                        enriched.setdefault("verified_value", m_info.get("value"))
                        enriched.setdefault("unit", m_info.get("unit", "USD"))
                        if res_data.get("as_of"):
                            enriched.setdefault("as_of", res_data.get("as_of"))
                        matched_live = True
                        break
                if matched_live:
                    break

    return enriched


def verify_citations(
    output: dict[str, Any], tool_results: dict[str, Any]
) -> dict[str, Any]:
    """
    Guards the LLM output by verifying that narrative quotes match retrieved chunks
    and that numeric data was properly fetched via tools.
    """
    if not isinstance(output, dict) or "citations" not in output:
        return output

    valid_citations, invalid_citations = check_citations(output, tool_results)
    enriched_valid = [_enrich_citation(c, tool_results) for c in valid_citations]

    if invalid_citations:
        output["answer"] = "I couldn't fully verify this response."
        output["citations"] = enriched_valid
    else:
        output["citations"] = enriched_valid

    return output
