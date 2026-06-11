def verify_citations(output: dict, tool_results: dict) -> dict:
    """
    Guards the LLM output by verifying that narrative quotes exactly match the retrieved chunks,
    and that numeric data was properly fetched
    """
    if not isinstance(output, dict) or "citations" not in output:
        return output

    valid_citations = []
    fabricated = False
    answer = output.get("answer", "")

    for citation in output.get("citations", []):
        cit_type = citation.get("type")
        is_valid = False

        if cit_type == "narrative":
            quote = citation.get("quote", "").strip()
            if not quote:
                fabricated = True
                continue

            clean_quote = " ".join(quote.split())

            for res_data in tool_results.values():
                # search_filings returns a list of dicts
                if isinstance(res_data, list):
                    for item in res_data:
                        if isinstance(item, dict) and "chunk_text" in item:
                            clean_chunk = " ".join(item["chunk_text"].split())
                            if clean_quote in clean_chunk:
                                is_valid = True
                                break
                if is_valid:
                    break

        elif cit_type == "numeric":
            concept = citation.get("concept")
            year = citation.get("year")

            for res_data in tool_results.values():
                # get_financial_data returns a dict
                if isinstance(res_data, dict):
                    if res_data.get("concept") == concept and str(
                        res_data.get("period")
                    ) == str(year):
                        val = res_data.get("value")
                        if val is not None:
                            val_str = (
                                str(val).replace(".", "").replace("-", "").lstrip("0")
                            )
                            sig_digits = val_str[:3]
                            if sig_digits in answer.replace(".", "").replace(",", ""):
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
