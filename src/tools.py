import ast
import operator
import re
from typing import Any

from edgar import Company, set_identity
from rank_bm25 import BM25Okapi

from src.config import (
    EDGAR_IDENTITY,
    EMBEDDING_DEVICE,
    EMBEDDING_MODEL,
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
