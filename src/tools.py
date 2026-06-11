import os
import re
import ast
import operator
from typing import Any
from edgar import set_identity, Company

from src.embed import get_collection, MODEL_NAME
from sentence_transformers import SentenceTransformer

# Configure EDGAR identity
identity = os.getenv("EDGAR_IDENTITY", "CompanyScope TestBot contact@example.com")
set_identity(identity)


def get_financial_data(ticker: str, concept: str, year) -> dict:
    """
    Fetches the financial fact for a given ticker, concept, and year.
    Returns a dict with concept, value, unit, period or an error.
    """
    try:
        company = Company(ticker)
        # Fetch the 10-K for the specified year
        # SEC filings for a year might be filed early the next year.
        # But edgartools filter by filing date. Usually a 10-K for 2023 is filed in late 2023 or early 2024.
        # To be safe, we can just get recent 10-Ks and find the one covering the year,
        # or we just get all 10-Ks and look at their reporting period.
        filings = company.get_filings(form="10-K")

        # Try to find the filing whose reporting date ends in the specified year
        target_filing = None
        for filing in filings:
            # We can parse the report date
            if filing.report_date and str(filing.report_date).startswith(str(year)):
                target_filing = filing
                break

        if not target_filing:
            # Fallback to filing date if report_date is not easily matching
            for filing in filings:
                if str(filing.filing_date).startswith(str(year)):
                    target_filing = filing
                    break

        if not target_filing:
            return {"error": f"10-K filing for {year} not found"}

        tenk = target_filing.obj()
        if not tenk or not hasattr(tenk, "financials"):
            return {"error": "Financials not available in the filing"}

        financials = tenk.financials
        if not financials:
            return {"error": "Financials data is empty"}

        # Map the concept to the appropriate edgartools Financials method
        # Also support passing the exact method name
        concept_lower = concept.lower().replace(" ", "_")
        method_name = None

        method_mapping = {
            "revenues": "get_revenue",
            "revenue": "get_revenue",
            "netincomeloss": "get_net_income",
            "net_income": "get_net_income",
            "operatingincomeloss": "get_operating_income",
            "operating_income": "get_operating_income",
            "assets": "get_total_assets",
            "total_assets": "get_total_assets",
            "liabilities": "get_total_liabilities",
            "total_liabilities": "get_total_liabilities",
            "stockholdersequity": "get_stockholders_equity",
            "stockholders_equity": "get_stockholders_equity",
            "operatingcashflow": "get_operating_cash_flow",
            "freecashflow": "get_free_cash_flow",
            "capitalexpenditures": "get_capital_expenditures",
            "currentassets": "get_current_assets",
            "currentliabilities": "get_current_liabilities",
        }

        if concept_lower in method_mapping:
            method_name = method_mapping[concept_lower]
        elif concept_lower.startswith("get_"):
            method_name = concept_lower
        elif hasattr(financials, f"get_{concept_lower}"):
            method_name = f"get_{concept_lower}"

        if not method_name or not hasattr(financials, method_name):
            return {"error": f"Concept '{concept}' not supported or not found."}
        method = getattr(financials, method_name)
        value = method()
        if value is None:
            return {"error": "Not found"}

        # edgartools financials methods often return strings or formatted numbers.
        val_str = str(value).replace(",", "")
        try:
            val_float = float(val_str)
        except ValueError:
            val_float = value

        return {
            "concept": concept,
            "value": val_float,
            "unit": "USD",
            "period": f"{year}",
        }

    except Exception as e:
        return {"error": f"Failed to get financial data: {str(e)}"}


# global model instance to avoid reloading
global_model = None


def search_filings(
    query: str, ticker: str | None = None, year: str | None = None, section: str | None = None, k: int = 3
) -> list[dict[str, Any]]:
    """
    Performs a semantic search on the SEC filings ChromaDB collection. (normal rag)
    """
    global global_model
    try:
        collection = get_collection()

        if global_model is None:
            global_model = SentenceTransformer(MODEL_NAME, device="cpu")

        query_embedding = global_model.encode([query]).tolist()

        # Build metadata filter
        where_clause: dict[str, Any] = {}
        conditions: list[dict[str, Any]] = []

        if ticker:
            conditions.append({"ticker": ticker.upper()})
        if year:
            conditions.append({"year": int(year)})
        if section:
            conditions.append({"section": section})

        if len(conditions) == 1:
            where_clause = conditions[0]
        elif len(conditions) > 1:
            where_clause = {"$and": conditions}

        # Execute query
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=k,
            where=where_clause if where_clause else None,
        )

        formatted_results: list[dict[str, Any]] = []
        if not results or not results["documents"] or not results["documents"][0]:
            return formatted_results

        docs = results["documents"][0]
        metadatas = results["metadatas"][0]

        for doc, meta in zip(docs, metadatas):
            formatted_results.append(
                {
                    "chunk_text": doc,
                    "ticker": meta.get("ticker"),
                    "year": meta.get("year"),
                    "section": meta.get("section"),
                    "chunk_id": meta.get("chunk_id"),
                }
            )

        return formatted_results

    except Exception as e:
        print(f"Search error: {e}")
        return []


def calculator(expression: str) -> float:
    # Verify characters are safe
    if not re.match(r"^[\d\+\-\*\/\%\(\)\.\s]+$", expression):
        raise ValueError(
            "Invalid characters in expression. Only digits and basic operators allowed."
        )

    # Supported operators for safe eval
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def eval_node(node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.BinOp):
            return operators[type(node.op)](eval_node(node.left), eval_node(node.right))
        elif isinstance(node, ast.UnaryOp):
            return operators[type(node.op)](eval_node(node.operand))
        else:
            raise TypeError(f"Unsupported operation: {type(node).__name__}")

    try:
        parsed_ast = ast.parse(expression, mode="eval")
        return float(eval_node(parsed_ast.body))
    except Exception as e:
        raise ValueError(f"Failed to evaluate expression '{expression}': {str(e)}")
