import ast
import datetime
import operator
import re
from typing import Any

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
from edgar import Company, set_identity
from src.db import (
    get_cached_financials,
    get_market_cache,
    has_ticker_chunks_pg,
    hybrid_search_pg,
    set_cached_financials,
    set_market_cache,
)
from src.embed import (
    _load_chunks_from_jsonl,
    build_index,
    get_collection,
    get_embedding_model,
    is_cloud_vector_enabled,
    is_local_chroma_available,
)
from src.embeddings import embed_query_cloud, get_active_embedding_model_name
from src.ingest import ingest_company
from src.market import fetch_fresh_news_and_sentiment

# Configure EDGAR identity
set_identity(EDGAR_IDENTITY)

_auto_ingested_tickers: set[str] = set()


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


STATEMENT_CONCEPT_ALIASES: dict[str, list[str]] = {
    "revenues": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenuesNetOfInterestExpense",
        "Revenues",
        "SalesRevenueNet",
    ],
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenuesNetOfInterestExpense",
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
        if year_str.lower() in ("", "latest", "recent", "current", "fy"):
            if len(filings) > 0:
                target_filing = filings[0]
                year_str = str(
                    target_filing.report_date or target_filing.filing_date
                )[:4]
        else:
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
            avail = [
                str(f.report_date or f.filing_date)[:4] for f in list(filings)[:5]
            ]
            return {
                "error": f"10-K filing for {year_str} not found. Available 10-K years for {ticker}: {', '.join(avail)}"
            }

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
        if method_name == "get_revenue":
            # Banks report top-line Total Net Revenue under RevenuesNetOfInterestExpense
            bank_rev = _lookup_concept_in_statements(
                financials, "RevenuesNetOfInterestExpense", year_str
            )
            if bank_rev is not None:
                value = bank_rev
        if value is None and method_name and hasattr(financials, method_name):
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


def _enrich_statement_row(base: dict[str, Any]) -> dict[str, Any]:
    """Computes derived margins, Free Cash Flow, Net Cash, ROE, and Debt/Equity from raw XBRL lines."""
    rev = base.get("Revenue")
    gp = base.get("Gross Profit")
    op = base.get("Operating Income")
    ni = base.get("Net Income")
    ocf = base.get("Operating Cash Flow")
    capex = base.get("CapEx")
    cash = base.get("Cash & Equivalents")
    debt = base.get("Long-Term Debt")
    eq = base.get("Stockholders Equity")

    fcf = base.get("Free Cash Flow")
    if fcf is None and ocf is not None:
        fcf = (ocf - abs(capex)) if capex is not None else ocf
        base["Free Cash Flow"] = fcf

    if cash is not None or debt is not None:
        base["Net Cash"] = (cash or 0.0) - abs(debt or 0.0)
    else:
        base["Net Cash"] = None

    def _pct(num: float | None, den: float | None) -> float | None:
        if num is None or den is None or abs(den) == 0:
            return None
        return round((num / den) * 100.0, 2)

    base["Gross Margin %"] = _pct(gp, rev)
    base["Operating Margin %"] = _pct(op, rev)
    base["Net Margin %"] = _pct(ni, rev)
    base["FCF Margin %"] = _pct(fcf, rev)
    base["ROE %"] = _pct(ni, eq) if (eq is not None and eq > 0) else None
    base["Debt / Equity"] = (
        round(abs(debt) / eq, 2)
        if (debt is not None and eq is not None and eq > 0)
        else None
    )
    return base


def _extract_facts_bundle(
    clean_ticker: str, years: list[int] | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Extracts full 5-year Annual (10-K) AND 6-quarter (10-Q) XBRL Income Statement,
    Balance Sheet, Cash Flow, and Ratio tables in a single ~0.5s SEC CompanyFacts call.
    """
    import pandas as pd

    facts_obj = Company(clean_ticker).get_facts()
    if facts_obj is None or not hasattr(facts_obj, "to_dataframe"):
        return [], []
    df = facts_obj.to_dataframe()
    if df is None or df.empty:
        return [], []

    work = df.dropna(subset=["numeric_value", "period_end"]).copy()
    if work.empty:
        return [], []

    work["pe_dt"] = pd.to_datetime(work["period_end"], errors="coerce")
    work["ps_dt"] = pd.to_datetime(work["period_start"], errors="coerce")
    work = work.dropna(subset=["pe_dt"])
    work["days"] = (work["pe_dt"] - work["ps_dt"]).dt.days
    work["yr"] = work["pe_dt"].dt.year
    work["ym"] = work["pe_dt"].dt.strftime("%Y-%m")

    line_specs: list[tuple[str, tuple[str, ...], bool, str]] = [
        (
            "Revenue",
            (
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenuesNetOfInterestExpense",
                "Revenues",
                "SalesRevenueNet",
            ),
            True,
            "USD",
        ),
        (
            "Gross Profit",
            ("GrossProfit",),
            True,
            "USD",
        ),
        (
            "R&D Expense",
            ("ResearchAndDevelopmentExpense",),
            True,
            "USD",
        ),
        (
            "SG&A Expense",
            ("SellingGeneralAndAdministrativeExpense",),
            True,
            "USD",
        ),
        (
            "Operating Income",
            (
                "OperatingIncomeLoss",
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            ),
            True,
            "USD",
        ),
        (
            "Net Income",
            ("NetIncomeLoss", "ProfitLoss"),
            True,
            "USD",
        ),
        (
            "Diluted EPS",
            ("EarningsPerShareDiluted", "EarningsPerShareBasic"),
            True,
            "USD per share",
        ),
        (
            "Cash & Equivalents",
            (
                "CashCashEquivalentsAndShortTermInvestments",
                "CashAndCashEquivalentsAtCarryingValue",
                "CashAndDueFromBanks",
            ),
            False,
            "USD",
        ),
        ("Total Assets", ("Assets",), False, "USD"),
        (
            "Long-Term Debt",
            (
                "LongTermDebtNoncurrent",
                "LongTermDebt",
                "LongTermDebtAndCapitalLeaseObligations",
            ),
            False,
            "USD",
        ),
        ("Total Liabilities", ("Liabilities",), False, "USD"),
        (
            "Stockholders Equity",
            (
                "StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            ),
            False,
            "USD",
        ),
        (
            "Operating Cash Flow",
            ("NetCashProvidedByUsedInOperatingActivities",),
            True,
            "USD",
        ),
        (
            "CapEx",
            (
                "PaymentsToAcquirePropertyPlantAndEquipment",
                "PaymentsToAcquireProductiveAssets",
            ),
            True,
            "USD",
        ),
        (
            "Share Repurchases",
            ("PaymentsForRepurchaseOfCommonStock",),
            True,
            "USD",
        ),
        (
            "Dividends Paid",
            (
                "PaymentsOfDividendsCommonStock",
                "PaymentsOfDividends",
            ),
            True,
            "USD",
        ),
    ]

    # 1. Annual (FY) extraction
    fy_df = work[work["fiscal_period"] == "FY"]
    annual_maps: dict[str, dict[int, float]] = {}
    for label, suffixes, is_flow, unit_filter in line_specs:
        sub = fy_df[fy_df["unit"] == unit_filter]
        if is_flow:
            sub = sub[(sub["days"] >= 330) & (sub["days"] <= 385)]
        else:
            sub = sub[sub["days"].isna()]
        out_yr: dict[int, float] = {}
        for suf in suffixes:
            matched = sub[
                sub["concept"].str.endswith(f":{suf}") | (sub["concept"] == suf)
            ]
            if matched.empty:
                continue
            grouped = (
                matched.sort_values("pe_dt")
                .groupby("yr")["numeric_value"]
                .last()
                .to_dict()
            )
            for k_yr, v_num in grouped.items():
                yi = int(k_yr)
                if yi not in out_yr and pd.notna(v_num):
                    out_yr[yi] = float(v_num)
        annual_maps[label] = out_yr

    all_yrs = sorted(
        set(annual_maps["Revenue"])
        | set(annual_maps["Net Income"])
        | set(annual_maps["Operating Income"])
        | set(annual_maps["Operating Cash Flow"])
    )
    chosen_yrs = (
        [y for y in years if y in all_yrs] if years is not None else all_yrs[-5:]
    )

    annual_rows: list[dict[str, Any]] = []
    for yr in chosen_yrs:
        row_a: dict[str, Any] = {
            "year": yr,
            "period": f"FY{str(yr)[-2:]}",
        }
        for label, _, _, _ in line_specs:
            val = annual_maps[label].get(yr)
            if label in ("CapEx", "Share Repurchases", "Dividends Paid") and val is not None:
                val = abs(val)
            row_a[label] = round(val, 2) if (label == "Diluted EPS" and val is not None) else val
        annual_rows.append(_enrich_statement_row(row_a))

    # 2. Quarterly (~90-day 10-Q/comparative) extraction keyed by YYYY-MM
    q_flow = work[
        work["fiscal_period"].isin(["Q1", "Q2", "Q3", "Q4"])
        & (work["days"] >= 75)
        & (work["days"] <= 105)
    ]
    q_inst = work[work["days"].isna()]

    q_maps: dict[str, dict[str, float]] = {}
    q_fp_labels: dict[str, str] = {}
    if not q_flow.empty:
        fp_grp = (
            q_flow.sort_values("pe_dt")
            .groupby("ym")["fiscal_period"]
            .last()
            .to_dict()
        )
        for ym_k, fp_v in fp_grp.items():
            q_fp_labels[str(ym_k)] = f"{fp_v} '{str(ym_k)[2:4]}"

    # Quarterly cash flows in 10-Qs are often reported YTD (90d Q1, 180d Q2, 270d Q3) or 90d standalone;
    # capture standalone 75-105d flows seamlessly
    for label, suffixes, is_flow, unit_filter in line_specs:
        base_q = q_flow if is_flow else q_inst
        sub_q = base_q[base_q["unit"] == unit_filter]
        out_ym: dict[str, float] = {}
        for suf in suffixes:
            matched = sub_q[
                sub_q["concept"].str.endswith(f":{suf}") | (sub_q["concept"] == suf)
            ]
            if matched.empty:
                continue
            grouped_q = (
                matched.sort_values("pe_dt")
                .groupby("ym")["numeric_value"]
                .last()
                .to_dict()
            )
            for k_ym, v_num in grouped_q.items():
                ym_s = str(k_ym)
                if ym_s not in out_ym and pd.notna(v_num):
                    out_ym[ym_s] = float(v_num)
        q_maps[label] = out_ym

    all_yms = sorted(
        set(q_maps["Revenue"]) | set(q_maps["Net Income"])
    )
    chosen_yms = all_yms[-6:]
    quarterly_rows: list[dict[str, Any]] = []
    for ym in chosen_yms:
        yr_int = int(ym[:4])
        row_q: dict[str, Any] = {
            "year": yr_int,
            "period": q_fp_labels.get(ym, ym),
            "period_end": ym,
        }
        for label, _, _, _ in line_specs:
            val_q = q_maps[label].get(ym)
            if label in ("CapEx", "Share Repurchases", "Dividends Paid") and val_q is not None:
                val_q = abs(val_q)
            row_q[label] = (
                round(val_q, 2)
                if (label == "Diluted EPS" and val_q is not None)
                else val_q
            )
        quarterly_rows.append(_enrich_statement_row(row_q))

    return annual_rows, quarterly_rows


def get_company_financial_bundle(ticker: str) -> dict[str, Any]:
    """Returns 24h-cached Annual (5Y 10-K) and Quarterly (6Q 10-Q) multi-statement XBRL tables."""
    clean_ticker = ticker.upper().strip()
    bundle_key = f"fin_bundle_v2:{clean_ticker}"
    cached_bundle = get_market_cache(bundle_key, ttl_seconds=86400)
    if isinstance(cached_bundle, dict) and cached_bundle.get("annual"):
        return cached_bundle

    try:
        annual_rows, quarterly_rows = _extract_facts_bundle(clean_ticker)
        if annual_rows:
            bundle = {
                "ticker": clean_ticker,
                "annual": annual_rows,
                "quarterly": quarterly_rows,
            }
            set_market_cache(bundle_key, bundle)
            set_cached_financials(clean_ticker, annual_rows)
            return bundle
    except Exception:
        pass

    fallback_annual = get_company_financial_summary(clean_ticker)
    return {
        "ticker": clean_ticker,
        "annual": fallback_annual,
        "quarterly": [],
    }


def get_company_financial_summary(
    ticker: str, years: list[int] | None = None
) -> list[dict[str, Any]]:
    """Fetches a multi-year table of core financial metrics for dashboard visualization (24h cached)."""
    clean_ticker = ticker.upper().strip()
    if years is None:
        cached = get_cached_financials(clean_ticker)
        if (
            cached is not None
            and len(cached) >= 2
            and "Gross Margin %" in cached[-1]
        ):
            return cached

    try:
        annual_rows, quarterly_rows = _extract_facts_bundle(clean_ticker, years=years)
        if annual_rows:
            if years is None:
                set_cached_financials(clean_ticker, annual_rows)
                set_market_cache(
                    f"fin_bundle_v2:{clean_ticker}",
                    {
                        "ticker": clean_ticker,
                        "annual": annual_rows,
                        "quarterly": quarterly_rows,
                    },
                )
            return annual_rows
    except Exception:
        pass

    current_yr = datetime.datetime.now(datetime.timezone.utc).year
    target_years = years or list(range(current_yr - 4, current_yr + 1))
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
            res = get_financial_data(clean_ticker, concept_key, yr)
            val = res.get("value") if "error" not in res else None
            row[label] = val
            if isinstance(val, (int, float)):
                has_any = True
        if has_any:
            rows.append(row)

    if years is None and rows:
        set_cached_financials(clean_ticker, rows)
    return rows


def _default_auto_ingest_years(year: str | int | None = None) -> list[int]:
    if year is not None and str(year).strip():
        try:
            return [int(str(year).strip())]
        except ValueError:
            pass
    cur = datetime.datetime.now(datetime.timezone.utc).year
    return [cur - 1, cur]


def _bm25_jsonl_fallback(
    query: str,
    ticker: str | None,
    year: str | int | None,
    section: str | None,
    k_limit: int,
) -> list[dict[str, Any]]:
    """Zero-DB lexical fallback over bundled/ingested chunks.jsonl when neither Postgres nor Chroma is active."""
    rows = _load_chunks_from_jsonl(ticker_filter=ticker)
    if not rows and ticker and ticker not in _auto_ingested_tickers:
        _auto_ingested_tickers.add(ticker)
        try:
            ingest_company(ticker=ticker, years=_default_auto_ingest_years(year))
            rows = _load_chunks_from_jsonl(ticker_filter=ticker)
        except Exception:
            rows = []
    if not rows:
        return []
    year_int: int | None = None
    if year is not None and str(year).strip():
        try:
            year_int = int(str(year).strip())
        except ValueError:
            year_int = None

    sec_clean: str | None = None
    if section and str(section).strip():
        sec_clean = str(section).strip()
        if not sec_clean.lower().startswith("item"):
            sec_clean = f"Item {sec_clean}"

    filtered = [
        r
        for r in rows
        if (year_int is None or int(r["year"]) == year_int)
        and (sec_clean is None or str(r["section"]) == sec_clean)
    ]
    if not filtered and sec_clean is not None:
        filtered = [
            r for r in rows if (year_int is None or int(r["year"]) == year_int)
        ]
    if not filtered:
        return []

    tokenized = [_tokenize(r["chunk_text"]) for r in filtered]
    q_tokens = _tokenize(query)
    if not q_tokens or not any(tokenized):
        return [
            {
                "chunk_text": r["chunk_text"],
                "ticker": r["ticker"],
                "year": r["year"],
                "section": r["section"],
                "chunk_id": r["chunk_id"],
                "chunk_level": r.get("chunk_level", "leaf"),
            }
            for r in filtered[:k_limit]
        ]

    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(q_tokens)
    ranked = sorted(
        zip(scores, filtered), key=lambda x: x[0], reverse=True
    )[:k_limit]
    return [
        {
            "chunk_text": r["chunk_text"],
            "ticker": r["ticker"],
            "year": r["year"],
            "section": r["section"],
            "chunk_id": r["chunk_id"],
            "chunk_level": r.get("chunk_level", "leaf"),
        }
        for _, r in ranked
    ]


def search_filings(
    query: str,
    ticker: str | None = None,
    year: str | int | None = None,
    section: str | None = None,
    k: int | None = None,
) -> list[dict[str, Any]]:
    """
    Performs a Hybrid RAG search (Dense Embeddings + Lexical Search with RRF fusion) over:
    1. Cloud Postgres (pgvector + tsvector) with Gemini Embedding 2 when configured
    2. Local ChromaDB + SentenceTransformers + BM25 in local dev
    3. Bundled chunks.jsonl BM25 fallback in zero-DB environments.
    """
    try:
        clean_ticker = str(ticker).upper().strip() if ticker else None
        k_limit = int(k) if k is not None else SEARCH_RESULTS_LIMIT
        lf = get_langfuse()

        # 1. Cloud Vector Mode: Gemini Embedding 2 + Postgres (pgvector + tsvector RRF)
        if is_cloud_vector_enabled():
            if clean_ticker and clean_ticker not in _auto_ingested_tickers:
                if not has_ticker_chunks_pg(clean_ticker):
                    _auto_ingested_tickers.add(clean_ticker)
                    try:
                        existing_local = _load_chunks_from_jsonl(
                            ticker_filter=clean_ticker
                        )
                        if not existing_local:
                            ingest_company(
                                ticker=clean_ticker,
                                years=_default_auto_ingest_years(year),
                            )
                        build_index(ticker_filter=clean_ticker)
                    except Exception as auto_err:
                        print(
                            f"Cloud auto-ingestion skipped for {clean_ticker}: {auto_err}"
                        )

            active_emb_model = get_active_embedding_model_name()
            with obs_context(
                lf,
                as_type="embedding",
                name="embed-search-query-gemini",
                model=active_emb_model,
                input={"query": query},
                metadata={"provider": "google-gemini"},
            ) as emb_obs:
                q_vec = embed_query_cloud(query)
                if emb_obs is not None:
                    try:
                        emb_obs.update(
                            output={
                                "dimensions": len(q_vec),
                                "vector_preview": [round(v, 5) for v in q_vec[:5]],
                            },
                            usage_details={"input": len(_tokenize(query))},
                        )
                    except Exception:
                        pass

            pg_hits = hybrid_search_pg(
                query=query,
                query_vec=q_vec,
                ticker=clean_ticker,
                year=year,
                section=section,
                k_limit=k_limit,
            )
            if pg_hits:
                return pg_hits

        # 2. Zero-DB Serverless Fallback if local ChromaDB is not installed
        if not is_local_chroma_available():
            return _bm25_jsonl_fallback(
                query, clean_ticker, year, section, k_limit
            )

        # 3. Local Dev Mode: ChromaDB + SentenceTransformers + BM25 RRF
        collection = get_collection()

        # On-demand auto-ingestion if a requested ticker has 0 indexed chunks in ChromaDB
        if clean_ticker and clean_ticker not in _auto_ingested_tickers:
            existing_for_ticker = collection.get(
                where={"ticker": clean_ticker}, limit=1
            )
            if not (existing_for_ticker and existing_for_ticker.get("ids")):
                _auto_ingested_tickers.add(clean_ticker)
                try:
                    ingest_company(
                        ticker=clean_ticker,
                        years=_default_auto_ingest_years(year),
                    )
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
    Fetches fresh 24h-7d financial news (Google News RSS, Finnhub, Yahoo Finance) and
    recent investor discussions from Reddit (r/stocks, r/investing, r/wallstreetbets,
    r/SecurityAnalysis) ranked by BM25 relevance and recency.
    """
    return fetch_fresh_news_and_sentiment(ticker=ticker, query=query, limit=limit)


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
