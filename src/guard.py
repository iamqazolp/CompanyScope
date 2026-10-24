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


def verify_citations(output: dict[str, Any], tool_results: dict[str, Any]) -> dict[str, Any]:
    """
    Guards the LLM output by verifying that narrative quotes match retrieved chunks
    and that numeric data was properly fetched via tools.
    """
    if not isinstance(output, dict) or "citations" not in output:
        return output

    valid_citations: list[dict[str, Any]] = []
    fabricated = False
    answer = str(output.get("answer", ""))
    clean_answer_digits = answer.replace(".", "").replace(",", "")

    # Check if calculator was used in this turn
    has_calculator_result = any(
        isinstance(v, (int, float)) for v in tool_results.values()
    )

    for citation in output.get("citations", []):
        if not isinstance(citation, dict):
            continue
        cit_type = citation.get("type")
        is_valid = False

        if cit_type == "narrative":
            quote = str(citation.get("quote", "")).strip()
            if not quote:
                fabricated = True
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

        elif cit_type == "numeric":
            concept = _normalize_concept(citation.get("concept"))
            year = str(citation.get("year", "")).strip()

            for res_data in tool_results.values():
                if isinstance(res_data, dict) and "value" in res_data:
                    res_concept = _normalize_concept(res_data.get("concept"))
                    res_period = str(res_data.get("period", "")).strip()
                    concept_matches = (
                        not concept
                        or res_concept == concept
                        or concept in res_concept
                        or res_concept in concept
                    )
                    if concept_matches and res_period == year:
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

        if is_valid:
            valid_citations.append(citation)
        else:
            fabricated = True

    if fabricated:
        output["answer"] = "I couldn't fully verify this response."
        output["citations"] = valid_citations

    return output
