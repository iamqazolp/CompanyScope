import ast
import datetime
import operator
import re
from typing import Any
import xml.etree.ElementTree as ET

from edgar import Company, set_identity
from rank_bm25 import BM25Okapi
import requests

from src.config import (
    EDGAR_IDENTITY,
    EMBEDDING_DEVICE,
    EMBEDDING_MODEL,
    FINNHUB_API_KEY,
    FMP_API_KEY,
    SEARCH_RESULTS_LIMIT,
    get_langfuse,
    obs_context,
)
from src.embed import build_index, get_collection, get_embedding_model
from src.ingest import ingest_company

# Configure EDGAR identity
set_identity(EDGAR_IDENTITY)

_auto_ingested_tickers: set[str] = set()


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


STATEMENT_CONCEPT_ALIASES: dict[str, list[str]] = {
    "revenues": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "netincomeloss": ["NetIncomeLoss", "ProfitLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "operatingincomeloss": ["OperatingIncomeLoss"],
    "operating_income": ["OperatingIncomeLoss"],
    "grossprofit": ["GrossProfit"],
    "gross_profit": ["GrossProfit"],
    "gross_margin": ["GrossProfit"],
    "costofgoodsandservicessold": [
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
    ],
    "cost_of_sales": ["CostOfGoodsAndServicesSold", "CostOfRevenue"],
    "cogs": ["CostOfGoodsAndServicesSold", "CostOfRevenue"],
    "researchanddevelopmentexpense": ["ResearchAndDevelopmentExpense"],
    "research_and_development": ["ResearchAndDevelopmentExpense"],
    "r_d": ["ResearchAndDevelopmentExpense"],
    "rd_expense": ["ResearchAndDevelopmentExpense"],
    "sellinggeneralandadministrativeexpense": [
        "SellingGeneralAndAdministrativeExpense"
    ],
    "sga": ["SellingGeneralAndAdministrativeExpense"],
    "operatingexpenses": ["OperatingExpenses"],
    "operating_expenses": ["OperatingExpenses"],
    "earningspersharebasic": ["EarningsPerShareBasic"],
    "eps_basic": ["EarningsPerShareBasic"],
    "basic_eps": ["EarningsPerShareBasic"],
    "earningspersharediluted": ["EarningsPerShareDiluted"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "diluted_eps": ["EarningsPerShareDiluted"],
    "assets": ["Assets"],
    "total_assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "total_liabilities": ["Liabilities"],
    "stockholdersequity": ["StockholdersEquity"],
    "stockholders_equity": ["StockholdersEquity"],
    "cashandcashequivalentsatcarryingvalue": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "cash_and_equivalents": ["CashAndCashEquivalentsAtCarryingValue"],
    "inventorynet": ["InventoryNet"],
    "inventory": ["InventoryNet"],
    "inventories": ["InventoryNet"],
    "accountsreceivablenetcurrent": ["AccountsReceivableNetCurrent"],
    "accounts_receivable": ["AccountsReceivableNetCurrent"],
    "propertyplantandequipmentnet": ["PropertyPlantAndEquipmentNet"],
    "ppe": ["PropertyPlantAndEquipmentNet"],
    "longtermdebt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "term_debt": ["LongTermDebtNoncurrent", "LongTermDebtCurrent"],
    "total_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "retainedearnings": ["RetainedEarningsAccumulatedDeficit"],
    "retained_earnings": ["RetainedEarningsAccumulatedDeficit"],
    "operatingcashflow": ["NetCashProvidedByUsedInOperatingActivities"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "cash_flow_from_operations": ["NetCashProvidedByUsedInOperatingActivities"],
    "capitalexpenditures": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "capital_expenditures": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "depreciation": ["DepreciationDepletionAndAmortization"],
    "depreciation_and_amortization": ["DepreciationDepletionAndAmortization"],
    "sharebasedcompensation": ["ShareBasedCompensation"],
    "share_based_compensation": ["ShareBasedCompensation"],
    "sbc": ["ShareBasedCompensation"],
    "dividends": ["PaymentsOfDividends"],
    "dividends_paid": ["PaymentsOfDividends"],
    "sharerepurchases": ["PaymentsForRepurchaseOfCommonStock"],
    "share_repurchases": ["PaymentsForRepurchaseOfCommonStock"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
}


def _lookup_concept_in_statements(
    financials: Any, concept: str, year_str: str
) -> float | None:
    """Searches income statement, balance sheet, and cash flow statement DataFrames for a concept or label."""
    concept_lower = re.sub(r"[^a-z0-9]+", "_", concept.lower()).strip("_")
    concept_compact = concept_lower.replace("_", "")

    target_suffixes = STATEMENT_CONCEPT_ALIASES.get(
        concept_lower
    ) or STATEMENT_CONCEPT_ALIASES.get(concept_compact) or [concept]

    statement_fns = [
        getattr(financials, "income_statement", None),
        getattr(financials, "balance_sheet", None),
        getattr(financials, "cash_flow_statement", None),
    ]

    for fn in statement_fns:
        if not callable(fn):
            continue
        try:
            stmt = fn()
            if stmt is None or not hasattr(stmt, "to_dataframe"):
                continue
            df = stmt.to_dataframe()
            if df is None or df.empty:
                continue

            # Identify value columns (e.g. '2025-09-27 (FY)' or '2024-09-28')
            meta_cols = {
                "concept",
                "label",
                "standard_concept",
                "level",
                "abstract",
                "dimension",
                "is_breakdown",
                "dimension_axis",
                "dimension_member",
                "dimension_member_label",
                "dimension_label",
                "balance",
                "weight",
                "preferred_sign",
                "parent_concept",
                "parent_abstract_concept",
            }
            val_cols = [c for c in df.columns if c not in meta_cols]
            if not val_cols:
                continue

            chosen_col = val_cols[0]
            for vc in val_cols:
                if str(vc).startswith(year_str) or year_str in str(vc):
                    chosen_col = vc
                    break

            # 1. Exact/suffix match on XBRL concept column (prefer non-breakdown rows first)
            for allow_breakdown in (False, True):
                sub_df = (
                    df
                    if allow_breakdown or "is_breakdown" not in df.columns
                    else df[~df["is_breakdown"]]
                )
                for suf in target_suffixes:
                    suf_clean = suf.lower().replace("_", "")
                    for _, row in sub_df.iterrows():
                        raw_c = str(row.get("concept") or "")
                        c_tail = raw_c.split("_")[-1].lower()
                        if c_tail == suf_clean or raw_c.lower().endswith(
                            suf.lower()
                        ):
                            raw_val = row.get(chosen_col)
                            if raw_val is not None and str(raw_val) not in (
                                "nan",
                                "None",
                                "",
                            ):
                                try:
                                    return float(
                                        str(raw_val)
                                        .replace(",", "")
                                        .replace("$", "")
                                        .strip()
                                    )
                                except ValueError:
                                    pass

            # 2. Match on human-readable row label (e.g. 'iPhone', 'Services', 'Gross margin', 'Research and development')
            for _, row in df.iterrows():
                lbl = str(row.get("label") or "").strip().lower()
                lbl_norm = re.sub(r"[^a-z0-9]+", "_", lbl).strip("_")
                if (
                    lbl_norm == concept_lower
                    or lbl.replace(" ", "") == concept_compact
                    or (len(concept_lower) >= 4 and concept_lower in lbl_norm)
                ):
                    raw_val = row.get(chosen_col)
                    if raw_val is not None and str(raw_val) not in (
                        "nan",
                        "None",
                        "",
                    ):
                        try:
                            return float(
                                str(raw_val)
                                .replace(",", "")
                                .replace("$", "")
                                .strip()
                            )
                        except ValueError:
                            pass
        except Exception:
            continue

    return None


def get_financial_data(ticker: str, concept: str, year: int | str) -> dict[str, Any]:
    """
    Fetches the financial fact for a given ticker, concept, and year.
    Returns a dict with concept, value, unit, period or an error.
    """
    try:
        ticker = ticker.upper().strip()
        year_str = str(year).strip()
        company = Company(ticker)
        filings = company.get_filings(form="10-K")

        target_filing = None
        for filing in filings:
            if filing.report_date and str(filing.report_date).startswith(year_str):
                target_filing = filing
                break

        if not target_filing:
            for filing in filings:
                if str(filing.filing_date).startswith(year_str):
                    target_filing = filing
                    break

        if not target_filing:
            # Fallback to 10-Q filings if a 10-K for that year does not exist yet
            q_filings = company.get_filings(form="10-Q")
            for filing in q_filings:
                if (
                    filing.report_date
                    and str(filing.report_date).startswith(year_str)
                ) or str(filing.filing_date).startswith(year_str):
                    target_filing = filing
                    break

        if not target_filing:
            return {"error": f"10-K filing for {year_str} not found"}

        tenk = target_filing.obj()
        if not tenk or not hasattr(tenk, "financials"):
            return {"error": "Financials not available in the filing"}

        financials = tenk.financials
        if not financials:
            return {"error": "Financials data is empty"}

        concept_lower = re.sub(r"[^a-z0-9]+", "_", concept.lower()).strip("_")
        concept_compact = concept_lower.replace("_", "")
        method_name = None

        method_mapping = {
            "revenues": "get_revenue",
            "revenue": "get_revenue",
            "total_revenue": "get_revenue",
            "sales": "get_revenue",
            "netincomeloss": "get_net_income",
            "net_income": "get_net_income",
            "net_income_loss": "get_net_income",
            "profit": "get_net_income",
            "operatingincomeloss": "get_operating_income",
            "operating_income": "get_operating_income",
            "operating_profit": "get_operating_income",
            "assets": "get_total_assets",
            "total_assets": "get_total_assets",
            "liabilities": "get_total_liabilities",
            "total_liabilities": "get_total_liabilities",
            "stockholdersequity": "get_stockholders_equity",
            "stockholders_equity": "get_stockholders_equity",
            "shareholders_equity": "get_stockholders_equity",
            "equity": "get_stockholders_equity",
            "operatingcashflow": "get_operating_cash_flow",
            "operating_cash_flow": "get_operating_cash_flow",
            "cash_flow_from_operations": "get_operating_cash_flow",
            "freecashflow": "get_free_cash_flow",
            "free_cash_flow": "get_free_cash_flow",
            "capitalexpenditures": "get_capital_expenditures",
            "capital_expenditures": "get_capital_expenditures",
            "capex": "get_capital_expenditures",
            "currentassets": "get_current_assets",
            "current_assets": "get_current_assets",
            "currentliabilities": "get_current_liabilities",
            "current_liabilities": "get_current_liabilities",
            "shares_outstanding_basic": "get_shares_outstanding_basic",
            "shares_outstanding_diluted": "get_shares_outstanding_diluted",
        }

        if concept_lower in method_mapping:
            method_name = method_mapping[concept_lower]
        elif concept_compact in method_mapping:
            method_name = method_mapping[concept_compact]
        elif concept_lower.startswith("get_"):
            method_name = concept_lower
        elif hasattr(financials, f"get_{concept_lower}"):
            method_name = f"get_{concept_lower}"

        value = None
        if method_name and hasattr(financials, method_name):
            method = getattr(financials, method_name)
            value = method()

        # Fallback to XBRL statement DataFrames when helper method is missing or returns None
        if value is None:
            if concept_compact in ("freecashflow",):
                ocf = _lookup_concept_in_statements(
                    financials, "OperatingCashFlow", year_str
                )
                capex = _lookup_concept_in_statements(
                    financials, "CapitalExpenditures", year_str
                )
                if ocf is not None and capex is not None:
                    value = ocf - abs(capex)
            else:
                value = _lookup_concept_in_statements(
                    financials, concept, year_str
                )

        if value is None:
            return {"error": f"Concept '{concept}' not supported or not found."}

        val_str = str(value).replace(",", "").replace("$", "").strip()
        val_out: float | str
        try:
            val_out = float(val_str)
        except ValueError:
            val_out = str(value)

        return {
            "ticker": ticker,
            "concept": concept,
            "value": val_out,
            "unit": "USD",
            "period": year_str,
        }

    except Exception as e:
        return {"error": f"Failed to get financial data: {str(e)}"}


def get_company_financial_summary(
    ticker: str, years: list[int] | None = None
) -> list[dict[str, Any]]:
    """Fetches a multi-year table of core financial metrics for dashboard visualization."""
    target_years = years or [2021, 2022, 2023, 2024, 2025]
    metrics = [
        ("Revenue", "Revenues"),
        ("Net Income", "NetIncomeLoss"),
        ("Operating Income", "OperatingIncomeLoss"),
        ("Total Assets", "Assets"),
        ("Total Liabilities", "Liabilities"),
        ("Operating Cash Flow", "OperatingCashFlow"),
        ("Free Cash Flow", "FreeCashFlow"),
    ]
    rows: list[dict[str, Any]] = []
    for yr in target_years:
        row: dict[str, Any] = {"year": yr}
        has_any = False
        for label, concept_key in metrics:
            res = get_financial_data(ticker, concept_key, yr)
            val = res.get("value") if "error" not in res else None
            row[label] = val
            if isinstance(val, (int, float)):
                has_any = True
        if has_any:
            rows.append(row)
    return rows


def search_filings(
    query: str,
    ticker: str | None = None,
    year: str | int | None = None,
    section: str | None = None,
    k: int | None = None,
) -> list[dict[str, Any]]:
    """
    Performs a Hybrid RAG search (Dense Embeddings + BM25 Lexical Search with RRF fusion)
    over the SEC filings ChromaDB collection, including RAPTOR-lite section summaries.
    """
    try:
        collection = get_collection()
        clean_ticker = str(ticker).upper().strip() if ticker else None

        # On-demand auto-ingestion if a requested ticker has 0 indexed chunks in ChromaDB
        if clean_ticker and clean_ticker not in _auto_ingested_tickers:
            existing_for_ticker = collection.get(
                where={"ticker": clean_ticker}, limit=1
            )
            if not (existing_for_ticker and existing_for_ticker.get("ids")):
                _auto_ingested_tickers.add(clean_ticker)
                try:
                    target_yr = int(str(year).strip()) if year else None
                    yrs_to_ingest = (
                        [target_yr] if target_yr else [2023, 2024, 2025]
                    )
                    ingest_company(ticker=clean_ticker, years=yrs_to_ingest)
                    build_index(ticker_filter=clean_ticker)
                except Exception as auto_err:
                    print(
                        f"Auto-ingestion skipped for {clean_ticker}: {auto_err}"
                    )

        if collection.count() == 0:
            return []

        model = get_embedding_model()
        k_limit = int(k) if k is not None else SEARCH_RESULTS_LIMIT
        lf = get_langfuse()

        with obs_context(
            lf,
            as_type="embedding",
            name="embed-search-query",
            model=EMBEDDING_MODEL,
            input={"query": query},
            metadata={"device": EMBEDDING_DEVICE},
        ) as emb_obs:
            query_embedding = model.encode([query]).tolist()
            if emb_obs is not None and query_embedding:
                try:
                    emb_obs.update(
                        output={
                            "dimensions": len(query_embedding[0]),
                            "vector_preview": [
                                round(v, 5) for v in query_embedding[0][:5]
                            ],
                        },
                        usage_details={"input": len(_tokenize(query))},
                    )
                except Exception:
                    pass

        # Build metadata filter
        where_clause: dict[str, Any] = {}
        conditions: list[dict[str, Any]] = []

        if ticker:
            conditions.append({"ticker": str(ticker).upper().strip()})
        if year is not None and str(year).strip() != "":
            try:
                conditions.append({"year": int(str(year).strip())})
            except ValueError:
                pass
        if section and str(section).strip():
            sec_clean = str(section).strip()
            # Normalize e.g. "1A" -> "Item 1A" if user/LLM omitted "Item"
            if not sec_clean.lower().startswith("item"):
                sec_clean = f"Item {sec_clean}"
            conditions.append({"section": sec_clean})

        if len(conditions) == 1:
            where_clause = conditions[0]
        elif len(conditions) > 1:
            where_clause = {"$and": conditions}

        candidate_pool_size = max(k_limit * 4, 15)
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=candidate_pool_size,
            where=where_clause if where_clause else None,
        )

        # If strict section filter yielded nothing, retry without section filter
        if (
            (not results or not results.get("documents") or not results["documents"][0])
            and section
            and len(conditions) > 1
        ):
            fallback_conditions = [c for c in conditions if "section" not in c]
            fallback_where = (
                fallback_conditions[0]
                if len(fallback_conditions) == 1
                else {"$and": fallback_conditions}
            )
            results = collection.query(
                query_embeddings=query_embedding,
                n_results=candidate_pool_size,
                where=fallback_where if fallback_where else None,
            )

        if not results or not results.get("documents") or not results["documents"][0]:
            return []

        dense_docs = results["documents"][0]
        dense_metas = results["metadatas"][0]

        # Build candidate items keyed by chunk_id
        candidates: dict[str, dict[str, Any]] = {}
        dense_rank_map: dict[str, int] = {}

        for rank, (doc, meta) in enumerate(zip(dense_docs, dense_metas)):
            cid = str(meta.get("chunk_id", f"chunk_{rank}"))
            candidates[cid] = {
                "chunk_text": doc,
                "ticker": meta.get("ticker"),
                "year": meta.get("year"),
                "section": meta.get("section"),
                "chunk_id": cid,
                "chunk_level": meta.get("chunk_level", "leaf"),
            }
            dense_rank_map[cid] = rank

        # Also pull matching corpus from ChromaDB for full-recall BM25 lexical matching
        try:
            corpus_res = collection.get(
                where=where_clause if where_clause else None,
                include=["documents", "metadatas"],
            )
            corpus_docs = corpus_res.get("documents") or []
            corpus_metas = corpus_res.get("metadatas") or []
        except Exception:
            corpus_docs = dense_docs
            corpus_metas = dense_metas

        bm25_rank_map: dict[str, int] = {}
        if corpus_docs:
            tokenized_corpus = [_tokenize(d) for d in corpus_docs]
            query_tokens = _tokenize(query)
            if query_tokens and any(tokenized_corpus):
                bm25 = BM25Okapi(tokenized_corpus)
                scores = bm25.get_scores(query_tokens)
                ranked_indices = sorted(
                    range(len(scores)), key=lambda i: scores[i], reverse=True
                )[:candidate_pool_size]

                for rank, idx in enumerate(ranked_indices):
                    if scores[idx] <= 0:
                        continue
                    meta = corpus_metas[idx] or {}
                    doc = corpus_docs[idx]
                    cid = str(meta.get("chunk_id", f"bm25_{idx}"))
                    bm25_rank_map[cid] = rank
                    if cid not in candidates:
                        candidates[cid] = {
                            "chunk_text": doc,
                            "ticker": meta.get("ticker"),
                            "year": meta.get("year"),
                            "section": meta.get("section"),
                            "chunk_id": cid,
                            "chunk_level": meta.get("chunk_level", "leaf"),
                        }

        # Reciprocal Rank Fusion (RRF)
        rrf_k = 60
        is_broad_query = any(
            kw in query.lower()
            for kw in ("summarize", "summary", "overview", "tell me about", "main", "general")
        )

        scored_candidates: list[tuple[float, dict[str, Any]]] = []
        for cid, item in candidates.items():
            score = 0.0
            if cid in dense_rank_map:
                score += 1.0 / (rrf_k + dense_rank_map[cid] + 1)
            if cid in bm25_rank_map:
                score += 1.0 / (rrf_k + bm25_rank_map[cid] + 1)
            # Boost RAPTOR-lite summary chunks on broad/overview questions
            if is_broad_query and item.get("chunk_level") == "summary":
                score += 0.008
            scored_candidates.append((score, item))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored_candidates[:k_limit]]

    except Exception as e:
        print(f"Search error: {e}")
        return []


def get_earnings_transcripts(
    ticker: str,
    year: str | int | None = None,
    quarter: str | int | None = None,
    query: str | None = None,
    k: int = 4,
) -> list[dict[str, Any]]:
    """
    Fetches earnings call transcripts and SEC 8-K Item 2.02 (Exhibit 99.1) quarterly earnings releases
    with CEO/CFO commentary for a given company, optionally filtered by year, quarter, and search query.
    """
    clean_ticker = ticker.upper().strip()
    target_year: int | None = None
    if year is not None and str(year).strip():
        try:
            target_year = int(str(year).strip())
        except ValueError:
            target_year = None

    target_quarter: int | None = None
    if quarter is not None and str(quarter).strip():
        q_str = re.sub(r"[^0-9]", "", str(quarter))
        if q_str:
            try:
                target_quarter = int(q_str)
            except ValueError:
                target_quarter = None

    collected_chunks: list[dict[str, Any]] = []

    # 1. Optional Financial Modeling Prep (FMP) Transcript API if FMP_API_KEY is configured
    if FMP_API_KEY:
        try:
            fmp_yr = target_year or 2025
            fmp_q = target_quarter or 4
            url = (
                f"https://financialmodelingprep.com/api/v3/earning_call_transcript/"
                f"{clean_ticker}?year={fmp_yr}&quarter={fmp_q}&apikey={FMP_API_KEY}"
            )
            r = requests.get(url, timeout=10)
            if r.ok:
                data = r.json()
                if isinstance(data, list) and data:
                    content = str(data[0].get("content") or "").strip()
                    if content:
                        words = content.split()
                        for idx, i in enumerate(range(0, len(words), 400)):
                            piece = " ".join(words[i : i + 450])
                            collected_chunks.append(
                                {
                                    "chunk_id": f"{clean_ticker}_{fmp_yr}_Q{fmp_q}_TRANSCRIPT_{idx}",
                                    "chunk_text": piece,
                                    "ticker": clean_ticker,
                                    "year": fmp_yr,
                                    "section": f"Earnings Call Q{fmp_q}",
                                    "source_type": "earnings_call",
                                }
                            )
        except Exception:
            pass

    # 2. Optional Finnhub Transcripts API if FINNHUB_API_KEY is configured and FMP yielded nothing
    if not collected_chunks and FINNHUB_API_KEY:
        try:
            r_list = requests.get(
                f"https://finnhub.io/api/v1/stock/transcripts/list?symbol={clean_ticker}&token={FINNHUB_API_KEY}",
                timeout=10,
            )
            if r_list.ok:
                transcripts = (r_list.json() or {}).get("transcripts") or []
                for meta in transcripts[:4]:
                    t_yr = meta.get("year")
                    t_q = meta.get("quarter")
                    if target_year and t_yr != target_year:
                        continue
                    if target_quarter and t_q != target_quarter:
                        continue
                    t_id = meta.get("id")
                    if not t_id:
                        continue
                    r_tr = requests.get(
                        f"https://finnhub.io/api/v1/stock/transcripts?id={t_id}&token={FINNHUB_API_KEY}",
                        timeout=10,
                    )
                    if r_tr.ok:
                        tr_body = r_tr.json() or {}
                        speeches = tr_body.get("transcript") or []
                        full_text = "\n".join(
                            f"{s.get('name', 'Speaker')}: {' '.join(s.get('speech', []))}"
                            for s in speeches
                            if isinstance(s, dict)
                        )
                        words = full_text.split()
                        for idx, i in enumerate(range(0, len(words), 400)):
                            piece = " ".join(words[i : i + 450])
                            collected_chunks.append(
                                {
                                    "chunk_id": f"{clean_ticker}_{t_yr}_Q{t_q}_FINNHUB_{idx}",
                                    "chunk_text": piece,
                                    "ticker": clean_ticker,
                                    "year": t_yr or (target_year or 2025),
                                    "section": f"Earnings Call Q{t_q}",
                                    "source_type": "earnings_call",
                                }
                            )
                    break
        except Exception:
            pass

    # 3. Check indexed 8-K Item 2.02 (Exhibit 99.1 Earnings Releases) in ChromaDB
    if not collected_chunks:
        indexed_8k = search_filings(
            query=query or f"{clean_ticker} quarterly revenue gross margin CEO CFO commentary",
            ticker=clean_ticker,
            year=target_year,
            section="Item 2.02",
            k=k,
        )
        for item in indexed_8k:
            if item.get("section") == "Item 2.02":
                item["source_type"] = "earnings_release_8k"
                collected_chunks.append(item)

    # 4. Live SEC EDGAR 8-K Exhibit 99.1 Earnings Release fallback via edgartools
    if not collected_chunks:
        try:
            company = Company(clean_ticker)
            filings_8k = company.get_filings(form="8-K")
            fetched_releases = 0
            for f in filings_8k:
                f_yr = f.filing_date.year
                if target_year and f_yr != target_year:
                    continue
                try:
                    obj = f.obj()
                    items_list = getattr(obj, "items", []) or []
                    has_pr = getattr(obj, "has_press_release", False)
                    if "Item 2.02" not in items_list and not has_pr:
                        continue
                    text_blocks: list[str] = []
                    if has_pr and getattr(obj, "press_releases", None):
                        for pr in obj.press_releases:
                            pr_txt = str(pr.text() or "").strip()
                            if pr_txt:
                                text_blocks.append(pr_txt)
                    if not text_blocks and "Item 2.02" in items_list:
                        text_blocks.append(str(obj["Item 2.02"] or "").strip())

                    combined = "\n\n".join(t for t in text_blocks if t)
                    if not combined:
                        continue

                    acc_short = str(f.accession_no).split("-")[-1]
                    words = combined.split()
                    for idx, i in enumerate(range(0, len(words), 420)):
                        piece = " ".join(words[i : i + 480])
                        collected_chunks.append(
                            {
                                "chunk_id": f"{clean_ticker}_{f_yr}_8-K_{acc_short}_Item2.02_{idx}",
                                "chunk_text": piece,
                                "ticker": clean_ticker,
                                "year": f_yr,
                                "section": "Item 2.02",
                                "source_type": "earnings_release_8k",
                            }
                        )
                    fetched_releases += 1
                    if fetched_releases >= 3:
                        break
                except Exception:
                    continue
        except Exception:
            pass

    if not collected_chunks:
        return []

    # Rank chunks by BM25 relevance if a query was provided
    if query and len(collected_chunks) > k:
        tokenized_docs = [_tokenize(c["chunk_text"]) for c in collected_chunks]
        q_tokens = _tokenize(query)
        if q_tokens and any(tokenized_docs):
            bm25 = BM25Okapi(tokenized_docs)
            scores = bm25.get_scores(q_tokens)
            ranked = sorted(
                zip(scores, collected_chunks), key=lambda x: x[0], reverse=True
            )
            return [item for _, item in ranked[:k]]

    return collected_chunks[:k]


def get_market_sentiment(
    ticker: str,
    query: str | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """
    Fetches public market sentiment, retail investor discussions from Reddit
    (r/stocks, r/investing, r/wallstreetbets), and recent financial news headlines
    from Yahoo Finance for a given company ticker.
    """
    clean_ticker = ticker.upper().strip()
    search_term = f"{clean_ticker} {query}".strip() if query else clean_ticker
    headers = {
        "User-Agent": "python:companyscope:v0.2.0 (by /u/companyscope_research)"
    }
    items: list[dict[str, Any]] = []
    current_year = datetime.datetime.now(datetime.timezone.utc).year

    # 1. Reddit public JSON API across r/stocks, r/investing, r/wallstreetbets
    try:
        reddit_url = (
            "https://www.reddit.com/r/stocks+investing+wallstreetbets/search.json"
        )
        r_red = requests.get(
            reddit_url,
            params={
                "q": search_term,
                "restrict_sr": "on",
                "sort": "relevance",
                "t": "year",
                "limit": str(max(limit, 6)),
            },
            headers=headers,
            timeout=8,
        )
        if r_red.ok:
            children = ((r_red.json() or {}).get("data") or {}).get("children") or []
            for idx, child in enumerate(children):
                post = (child or {}).get("data") or {}
                title = " ".join(str(post.get("title") or "").split())
                selftext = " ".join(str(post.get("selftext") or "").split())
                if not title:
                    continue
                subreddit = str(post.get("subreddit_name_prefixed") or "r/stocks")
                score = int(post.get("score") or 0)
                num_comments = int(post.get("num_comments") or 0)
                created_utc = post.get("created_utc")
                post_year = (
                    datetime.datetime.fromtimestamp(
                        float(created_utc), tz=datetime.timezone.utc
                    ).year
                    if created_utc
                    else current_year
                )
                post_id = str(post.get("id") or idx)
                permalink = str(post.get("permalink") or "")
                post_url = (
                    f"https://www.reddit.com{permalink}" if permalink else ""
                )

                snippet = selftext[:450] if selftext else title
                chunk_text = (
                    f"[{subreddit} | Score: {score} | Comments: {num_comments}] "
                    f"Title: {title}. Post: {snippet}"
                )
                items.append(
                    {
                        "chunk_id": f"{clean_ticker}_{post_year}_REDDIT_{post_id}",
                        "chunk_text": chunk_text,
                        "ticker": clean_ticker,
                        "year": post_year,
                        "section": f"Reddit ({subreddit})",
                        "source_type": "social_sentiment",
                        "url": post_url,
                    }
                )
                if len(items) >= (limit // 2) + 1:
                    break
    except Exception:
        pass

    # 2. Yahoo Finance Search News JSON API
    try:
        yf_search_url = "https://query2.finance.yahoo.com/v1/finance/search"
        r_yf = requests.get(
            yf_search_url,
            params={"q": search_term, "newsCount": str(limit), "quotesCount": "0"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        if r_yf.ok:
            news_list = (r_yf.json() or {}).get("news") or []
            for idx, article in enumerate(news_list):
                title = " ".join(str(article.get("title") or "").split())
                if not title:
                    continue
                publisher = str(article.get("publisher") or "Yahoo Finance")
                link = str(article.get("link") or "")
                pub_time = article.get("providerPublishTime")
                art_year = (
                    datetime.datetime.fromtimestamp(
                        float(pub_time), tz=datetime.timezone.utc
                    ).year
                    if pub_time
                    else current_year
                )
                uuid_short = str(article.get("uuid") or idx)[:8]
                chunk_text = f"[News: {publisher}] Headline: {title}"
                items.append(
                    {
                        "chunk_id": f"{clean_ticker}_{art_year}_NEWS_{uuid_short}",
                        "chunk_text": chunk_text,
                        "ticker": clean_ticker,
                        "year": art_year,
                        "section": f"News ({publisher})",
                        "source_type": "financial_news",
                        "url": link,
                    }
                )
                if len(items) >= limit:
                    break
    except Exception:
        pass

    # 3. Yahoo Finance RSS Feed fallback if needed
    if len(items) < limit:
        try:
            rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={clean_ticker}&region=US&lang=en-US"
            r_rss = requests.get(
                rss_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8
            )
            if r_rss.ok and r_rss.text:
                root = ET.fromstring(r_rss.text)
                for idx, item_el in enumerate(root.findall(".//item")):
                    title = " ".join(
                        (item_el.findtext("title") or "").split()
                    )
                    desc = " ".join(
                        (item_el.findtext("description") or "").split()
                    )
                    link = (item_el.findtext("link") or "").strip()
                    if not title:
                        continue
                    chunk_text = (
                        f"[Yahoo Finance RSS] Headline: {title}. Summary: {desc[:350]}"
                        if desc
                        else f"[Yahoo Finance RSS] Headline: {title}"
                    )
                    items.append(
                        {
                            "chunk_id": f"{clean_ticker}_{current_year}_YFRSS_{idx}",
                            "chunk_text": chunk_text,
                            "ticker": clean_ticker,
                            "year": current_year,
                            "section": "Yahoo Finance News",
                            "source_type": "financial_news",
                            "url": link,
                        }
                    )
                    if len(items) >= limit:
                        break
        except Exception:
            pass

    return items[:limit]


def calculator(expression: str) -> float:
    """Safely evaluates simple arithmetic expressions (+, -, *, /, %, ())."""
    if not re.match(r"^[\d\+\-\*\/\%\(\)\.\s\,]+$", expression):
        raise ValueError(
            "Invalid characters in expression. Only digits and basic operators allowed."
        )

    clean_expr = expression.replace(",", "")

    operators: dict[type[Any], Any] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def eval_node(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        elif isinstance(node, ast.BinOp):
            return float(
                operators[type(node.op)](eval_node(node.left), eval_node(node.right))
            )
        elif isinstance(node, ast.UnaryOp):
            return float(operators[type(node.op)](eval_node(node.operand)))
        else:
            raise TypeError(f"Unsupported operation: {type(node).__name__}")

    try:
        parsed_ast = ast.parse(clean_expr, mode="eval")
        return float(eval_node(parsed_ast.body))
    except Exception as e:
        raise ValueError(f"Failed to evaluate expression '{expression}': {str(e)}")
