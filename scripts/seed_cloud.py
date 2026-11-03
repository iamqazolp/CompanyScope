import argparse

from src.config import INGEST_YEARS
from src.db import get_index_stats_pg, is_postgres_enabled
from src.embed import _load_chunks_from_jsonl, build_index
from src.embeddings import get_active_embedding_model_name, is_cloud_embedding_enabled
from src.ingest import ingest_company
from src.tools import get_company_financial_summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed cloud Postgres (pgvector + XBRL cache) using Gemini Embedding 2."
    )
    parser.add_argument(
        "--tickers",
        default="AAPL,MSFT,NVDA",
        help="Comma-separated list of tickers to ingest and index (default: AAPL,MSFT,NVDA)",
    )
    parser.add_argument(
        "--years",
        default=",".join(str(y) for y in INGEST_YEARS),
        help="Comma-separated fiscal years to ingest",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Only embed and index chunks already present in data/processed/chunks.jsonl",
    )
    args = parser.parse_args()

    if not is_postgres_enabled():
        raise SystemExit(
            "ERROR: DATABASE_URL (or POSTGRES_URL) is not set. Add your Vercel Neon Postgres URL to .env first."
        )
    if not is_cloud_embedding_enabled():
        raise SystemExit(
            "ERROR: GEMINI_API_KEY is not set. Add your Google AI Studio key to .env first."
        )

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]

    print(
        f"Seeding cloud database using {get_active_embedding_model_name()} for: {', '.join(tickers)}"
    )

    for ticker in tickers:
        existing_local = _load_chunks_from_jsonl(ticker_filter=ticker)
        if not args.skip_download and not existing_local:
            print(f"\n[1/3] Downloading & chunking SEC filings for {ticker} ({years})...")
            ingest_company(ticker=ticker, years=years)
        elif not args.skip_download and ticker != "AAPL":
            print(f"\n[1/3] Refreshing SEC filings for {ticker} ({years})...")
            ingest_company(ticker=ticker, years=years)
        else:
            print(
                f"\n[1/3] Using {len(existing_local)} existing local chunks for {ticker}."
            )

        print(f"[2/3] Embedding & upserting {ticker} chunks into cloud pgvector...")
        count = build_index(ticker_filter=ticker)
        print(f"      Indexed {count} chunks for {ticker}.")

        print(f"[3/3] Warming 24h XBRL financial summary cache for {ticker}...")
        rows = get_company_financial_summary(ticker)
        print(f"      Cached {len(rows)} fiscal years of XBRL metrics for {ticker}.")

    stats = get_index_stats_pg()
    print(f"\nDone! Cloud pgvector total chunks: {stats.get('total_chunks', 0)}")


if __name__ == "__main__":
    main()
