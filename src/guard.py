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
    }
    return aliases.get(c, c)


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

        if cit_type in ("narrative", "earnings", "sentiment"):
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

        elif cit_type == "numeric":
            concept = _normalize_concept(citation.get("concept"))
            year = str(citation.get("year", "")).strip()
            cit_ticker = str(citation.get("ticker", "")).upper().strip()

            for res_data in tool_results.values():
                if isinstance(res_data, dict) and "value" in res_data:
                    res_concept = _normalize_concept(res_data.get("concept"))
                    res_period = str(res_data.get("period", "")).strip()
                    res_ticker = str(res_data.get("ticker", "")).upper().strip()
                    ticker_matches = (
                        not cit_ticker or not res_ticker or cit_ticker == res_ticker
                    )
                    concept_matches = (
                        not concept
                        or res_concept == concept
                        or concept in res_concept
                        or res_concept in concept
                    )
                    if ticker_matches and concept_matches and res_period == year:
                        val = res_data.get("value")
                        if val is not None:
                            val_str = (
                                str(val).replace(".", "").replace("-", "").lstrip("0")
                            )
                            sig_digits_3 = val_str[:3]
                            sig_digits_2 = val_str[:2]
                            if (
                                (sig_digits_3 and sig_digits_3 in clean_answer_digits)
                                or (sig_digits_2 and sig_digits_2 in clean_answer_digits)
                                or has_calculator_result
                            ):
                                is_valid = True
                        break

            if not is_valid:
                invalid_citations.append(
                    {
                        "citation": citation,
                        "reason": "Numeric fact was not fetched via get_financial_data or digits do not match.",
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

    if cit_type in ("narrative", "earnings", "sentiment"):
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

    elif cit_type == "numeric":
        concept = _normalize_concept(enriched.get("concept"))
        year = str(enriched.get("year", "")).strip()
        cit_ticker = str(enriched.get("ticker", "")).upper().strip()
        for res_data in tool_results.values():
            if isinstance(res_data, dict) and "value" in res_data:
                res_concept = _normalize_concept(res_data.get("concept"))
                res_period = str(res_data.get("period", "")).strip()
                res_ticker = str(res_data.get("ticker", "")).upper().strip()
                ticker_ok = not cit_ticker or not res_ticker or cit_ticker == res_ticker
                concept_ok = (
                    not concept
                    or res_concept == concept
                    or concept in res_concept
                    or res_concept in concept
                )
                if ticker_ok and concept_ok and res_period == year:
                    enriched.setdefault("verified_value", res_data.get("value"))
                    enriched.setdefault("unit", res_data.get("unit", "USD"))
                    if res_data.get("filing_date"):
                        enriched.setdefault("filing_date", res_data.get("filing_date"))
                    if res_data.get("form"):
                        enriched.setdefault("form", res_data.get("form"))
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
