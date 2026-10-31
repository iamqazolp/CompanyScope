import json
import os
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from src.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHUNKS_FILE,
    EDGAR_IDENTITY,
    INGEST_TICKER,
    INGEST_YEARS,
    PROCESSED_DIR,
    RAW_DIR,
)
from edgar import Company, set_identity

# Configure EDGAR identity (Required by SEC)
set_identity(EDGAR_IDENTITY)


def download_filings(
    ticker: str, years: list[int], include_8k: bool = True
) -> list[str]:
    """Downloads 10-K, 10-Q, and material/earnings 8-K filings for the given ticker and years."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ticker = ticker.upper()

    company = Company(ticker)
    forms = ["10-K", "10-Q", "8-K"] if include_8k else ["10-K", "10-Q"]
    filings = company.get_filings(form=forms)

    downloaded_files: list[str] = []
    eightk_count_per_year: dict[int, int] = {}

    for filing in filings:
        report_dt = getattr(filing, "report_date", None)
        filing_dt = getattr(filing, "filing_date", None)

        # Prefer fiscal report period year for 10-K/10-Q when available
        rep_year: int | None = None
        if report_dt is not None:
            try:
                rep_year = int(str(report_dt)[:4])
            except ValueError:
                rep_year = None

        fil_year: int = filing_dt.year if filing_dt is not None else (rep_year or 0)
        target_year = rep_year if (rep_year in years) else fil_year

        if target_year not in years:
            continue

        raw_form = filing.form
        form = raw_form.replace("/", "-")
        if raw_form.startswith("8-K"):
            # Limit 8-Ks per year to keep ingestion fast and focused on earnings/material events
            if eightk_count_per_year.get(target_year, 0) >= 6:
                continue
            eightk_count_per_year[target_year] = (
                eightk_count_per_year.get(target_year, 0) + 1
            )

        filename = f"{ticker}_{target_year}_{form}_{filing.accession_no}.html"
        filepath = RAW_DIR / filename

        if not filepath.exists():
            try:
                html_content = filing.html()
                if raw_form.startswith("8-K"):
                    # Append Exhibit 99.1 earnings release text if attached
                    try:
                        obj8k = filing.obj()
                        if getattr(obj8k, "has_press_release", False):
                            prs = getattr(obj8k, "press_releases", None)
                            if prs and len(prs) > 0:
                                pr_text = str(prs[0].text() or "").strip()
                                if pr_text:
                                    html_content = (
                                        (html_content or "")
                                        + "\n<hr/>\n<p>Item 2.02. Results of Operations and Financial Condition (Exhibit 99.1 Earnings Release)</p>\n<pre>"
                                        + pr_text
                                        + "</pre>\n"
                                    )
                    except Exception:
                        pass
                if html_content:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(html_content)
            except Exception as e:
                print(f"Failed to download {filename}: {e}")
                continue
        if filepath.exists():
            downloaded_files.append(str(filepath))

    return downloaded_files


def _table_to_markdown(table: Tag) -> str:
    """Converts compact data tables into inline Markdown text, ignoring layout/TOC tables."""
    if table.find("table") is not None:
        return ""

    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [
            " ".join(cell.get_text(" ", strip=True).split())
            for cell in tr.find_all(["th", "td"])
        ]
        # Collapse adjacent duplicate symbols like "$" andempty cells
        non_empty = [c for c in cells if c and c not in ("$", "%", "(", ")")]
        if non_empty:
            rows.append(non_empty)

    if len(rows) < 2 or len(rows) > 35:
        return ""

    # Skip table of contents tables
    joined_preview = " ".join(" ".join(r) for r in rows[:5]).lower()
    if "item 1." in joined_preview and "item 1a." in joined_preview:
        return ""

    md_lines = []
    for row in rows:
        if len(row) >= 2:
            md_lines.append(" | ".join(row))

    if len(md_lines) < 2:
        return ""

    return "\n" + "\n".join(md_lines) + "\n"


def extract_sections(html_path: str | Path) -> dict[str, str]:
    """Extracts narrative sections (Item 1, 1A, 7, 7A, and 10-Q Item 2) from the HTML filing."""
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")

    # Convert compact financial/segment tables to readable lines and remove layout/TOC tables
    for table in list(soup.find_all("table")):
        if table.find("table") is not None:
            continue
        md_text = _table_to_markdown(table)
        if md_text:
            table.replace_with(md_text)
        else:
            table.decompose()

    text = soup.get_text(separator="\n")
    text = re.sub(r"\n\s*\n", "\n\n", text)

    sections: dict[str, str] = {}

    items_to_extract = {
        "Item 1": r"Item\s+1[\.\s:\-–—]+Business",
        "Item 1A": r"Item\s+1A[\.\s:\-–—]+Risk\s+Factors",
        "Item 7": r"Item\s+7[\.\s:\-–—]+Management['’]s\s+Discussion\s+and\s+Analysis",
        "Item 7A": r"Item\s+7A[\.\s:\-–—]+Quantitative\s+and\s+Qualitative\s+Disclosures",
        "Item 2": r"Item\s+2[\.\s:\-–—]+Management['’]s\s+Discussion\s+and\s+Analysis",
        "Item 2.02": r"Item\s+2\.02[\.\s:\-–—]+Results\s+of\s+Operations",
        "Item 1.01": r"Item\s+1\.01[\.\s:\-–—]+Entry\s+into\s+a\s+Material",
        "Item 5.02": r"Item\s+5\.02[\.\s:\-–—]+Departure\s+of\s+Directors",
        "Item 7.01": r"Item\s+7\.01[\.\s:\-–—]+Regulation\s+FD",
        "Item 8.01": r"Item\s+8\.01[\.\s:\-–—]+Other\s+Events",
    }

    item_regex = re.compile(
        r"\n\s*Item\s+(?:[0-9]{1,2}[A-B]?|[0-9]\.[0-9]{2})[\.\s:\-–—]+",
        re.IGNORECASE,
    )
    matches = list(item_regex.finditer(text))

    for target_key, target_pattern in items_to_extract.items():
        starts = list(re.finditer(target_pattern, text, re.IGNORECASE))
        if not starts:
            continue

        extracted_text = ""
        for start_match in starts:
            start_idx = start_match.start()
            end_idx = len(text)
            for match in matches:
                if match.start() > start_idx + 100:
                    end_idx = match.start()
                    break

            candidate_text = text[start_idx:end_idx].strip()
            if len(candidate_text) > len(extracted_text):
                extracted_text = candidate_text

        min_len = 100 if "." in target_key else 200
        if len(extracted_text) > min_len:
            sections[target_key] = extracted_text

    return sections


def build_raptor_section_summary(
    text: str,
    ticker: str,
    year: int,
    filing_type: str,
    section: str,
    max_words: int = 450,
    accession_suffix: str = "",
) -> dict[str, Any] | None:
    """
    RAPTOR-lite hierarchical summary node: selects representative verbatim sentences
    across clusters of paragraphs in a section so broad summary queries retrieve a
    section-wide overview while preserving 100% verbatim sentences for citation guard verification.
    """
    paragraphs = [
        " ".join(p.split())
        for p in text.split("\n\n")
        if len(p.split()) >= 12
    ]
    if len(paragraphs) < 3:
        return None

    # Sample evenly across the section to capture all major themes/clusters
    step = max(1, len(paragraphs) // 12)
    selected_sentences: list[str] = []
    word_count = 0

    for idx in range(0, len(paragraphs), step):
        para = paragraphs[idx]
        # Extract the lead sentence of the paragraph
        sentence_split = re.split(r"(?<=[.!?])\s+", para)
        lead_sentence = sentence_split[0].strip() if sentence_split else para
        if len(lead_sentence.split()) < 8:
            lead_sentence = para[:250].strip()

        s_words = len(lead_sentence.split())
        if word_count + s_words > max_words:
            break
        if lead_sentence not in selected_sentences:
            selected_sentences.append(lead_sentence)
            word_count += s_words

    if not selected_sentences:
        return None

    summary_text = " ".join(selected_sentences)
    acc_part = f"_{accession_suffix}" if accession_suffix else ""
    chunk_id = (
        f"{ticker}_{year}_{filing_type}{acc_part}_{section.replace(' ', '')}_SUMMARY"
    )
    return {
        "text": summary_text,
        "ticker": ticker,
        "year": year,
        "filing_type": filing_type,
        "section": section,
        "chunk_id": chunk_id,
        "chunk_level": "summary",
    }


def chunk_text(
    text: str,
    ticker: str,
    year: int,
    filing_type: str,
    section: str,
    chunk_size: int = 500,
    overlap: int = 50,
    accession_suffix: str = "",
) -> list[dict[str, Any]]:
    """Chunks text into leaf pieces plus a RAPTOR-lite hierarchical summary node."""
    words = text.split()
    chunks: list[dict[str, Any]] = []

    if not words:
        return chunks

    summary_chunk = build_raptor_section_summary(
        text=text,
        ticker=ticker,
        year=year,
        filing_type=filing_type,
        section=section,
        accession_suffix=accession_suffix,
    )
    if summary_chunk:
        chunks.append(summary_chunk)

    acc_part = f"_{accession_suffix}" if accession_suffix else ""
    step = max(1, chunk_size - overlap)
    for i in range(0, len(words), step):
        chunk_words = words[i : i + chunk_size]
        if not chunk_words:
            break

        chunk_str = " ".join(chunk_words)
        chunk_id = (
            f"{ticker}_{year}_{filing_type}{acc_part}_{section.replace(' ', '')}_{i}"
        )

        chunks.append(
            {
                "text": chunk_str,
                "ticker": ticker,
                "year": year,
                "filing_type": filing_type,
                "section": section,
                "chunk_id": chunk_id,
                "chunk_level": "leaf",
            }
        )

    return chunks


def ingest_company(
    ticker: str = INGEST_TICKER,
    years: list[int] | None = None,
) -> dict[str, Any]:
    """Downloads filings, extracts sections & tables, and updates chunks.jsonl for a ticker."""
    ticker = ticker.upper().strip()
    target_years = years if years is not None else INGEST_YEARS

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_file = CHUNKS_FILE

    # Preserve existing chunks from OTHER tickers for multi-ticker support
    existing_other_chunks: list[str] = []
    if out_file.exists():
        with open(out_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if data.get("ticker", "").upper() != ticker:
                        existing_other_chunks.append(line.rstrip("\n"))
                except json.JSONDecodeError:
                    continue

    print(f"Downloading filings for {ticker} ({target_years})...")
    html_paths = download_filings(ticker, target_years)
    print(f"Found {len(html_paths)} filings for {ticker}. Extracting and chunking...")

    new_chunks: list[dict[str, Any]] = []
    for path in html_paths:
        filename = os.path.basename(path)
        parts = filename.replace(".html", "").split("_")
        if len(parts) < 3:
            continue
        file_ticker = parts[0].upper()
        if file_ticker != ticker:
            continue
        year = int(parts[1])
        filing_type = parts[2]
        raw_accession = parts[3] if len(parts) > 3 else ""
        # Use short accession suffix on multi-filing forms (10-Q, 8-K) to prevent chunk_id collisions across quarters
        accession_suffix = (
            raw_accession.split("-")[-1]
            if (raw_accession and filing_type != "10-K")
            else ""
        )

        print(f"Processing {filename}...")
        sections = extract_sections(path)

        for section_name, section_text in sections.items():
            chunks = chunk_text(
                text=section_text,
                ticker=ticker,
                year=year,
                filing_type=filing_type,
                section=section_name,
                chunk_size=CHUNK_SIZE,
                overlap=CHUNK_OVERLAP,
                accession_suffix=accession_suffix,
            )
            new_chunks.extend(chunks)

    with open(out_file, "w", encoding="utf-8") as f:
        for raw_line in existing_other_chunks:
            f.write(raw_line + "\n")
        for chunk in new_chunks:
            f.write(json.dumps(chunk) + "\n")

    print(f"Completed {ticker}! Created {len(new_chunks)} chunks.")
    return {
        "ticker": ticker,
        "years": target_years,
        "filings_processed": len(html_paths),
        "chunks_created": len(new_chunks),
    }


if __name__ == "__main__":
    ingest_company(INGEST_TICKER, INGEST_YEARS)
