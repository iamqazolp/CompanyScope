import os
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from edgar import set_identity, Company

# Configure EDGAR identity (Required by SEC)
# It's good practice to set identity, using a generic one for now
set_identity(os.getenv("EDGAR_IDENTITY"))

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")


def download_filings(ticker: str, years: list[int]):
    """Downloads 10-K and 10-Q HTML filings for the given ticker and years."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    company = Company(ticker)
    filings = company.get_filings(form=["10-K", "10-Q"])

    downloaded_files = []

    for filing in filings:
        filing_year = filing.filing_date.year
        if filing_year in years:
            form = filing.form
            filename = f"{ticker}_{filing_year}_{form}_{filing.accession_no}.html"
            filepath = RAW_DIR / filename

            if not filepath.exists():
                try:
                    html_content = filing.html()
                    if html_content:
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(html_content)
                except Exception as e:
                    print(f"Failed to download {filename}: {e}")
                    continue
            downloaded_files.append(str(filepath))

    return downloaded_files


def extract_sections(html_path: str):
    """Extracts narrative sections (Item 1, 1A, 7, 7A) from the HTML filing."""
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")

    # Skip tables, cover pages, and exhibit indexes
    # Remove tables to skip tabular data and usually the TOC
    for table in soup.find_all("table"):
        table.decompose()

    text = soup.get_text(separator="\n")
    # Clean up excessive newlines and spaces
    text = re.sub(r"\n\s*\n", "\n\n", text)

    sections = {}

    # Heuristics for finding Items. We look for Item X. followed by a newline and the title or similar.
    # We use a pattern that allows spaces and punctuation.
    items_to_extract = {
        "Item 1": r"Item\s+1\.\s+Business",
        "Item 1A": r"Item\s+1A\.\s+Risk\s+Factors",
        "Item 7": r"Item\s+7\.\s+Management['’]s\s+Discussion\s+and\s+Analysis",
        "Item 7A": r"Item\s+7A\.\s+Quantitative\s+and\s+Qualitative\s+Disclosures",
    }

    # Generic item header regex to find the end of a section
    item_regex = re.compile(r"\n\s*Item\s+[0-9A-B]+\.\s+", re.IGNORECASE)
    matches = list(item_regex.finditer(text))

    for target_key, target_pattern in items_to_extract.items():
        # Find all occurrences of the target item header
        starts = list(re.finditer(target_pattern, text, re.IGNORECASE))

        if not starts:
            continue

        # If multiple starts, the last one is usually the actual section, not the TOC.
        # But we also verify it by checking the length of the extracted text.
        extracted_text = ""

        for start_match in starts:
            start_idx = start_match.start()

            end_idx = len(text)
            for match in matches:
                if match.start() > start_idx + 100:  # Ensure it's not matching itself
                    end_idx = match.start()
                    break

            candidate_text = text[start_idx:end_idx].strip()
            # If the text is reasonably long, it's likely the actual section
            if len(candidate_text) > len(extracted_text):
                extracted_text = candidate_text

        if len(extracted_text) > 200:  # Arbitrary threshold to ignore TOC mentions
            sections[target_key] = extracted_text

    return sections


def chunk_text(
    text: str,
    ticker: str,
    year: int,
    filing_type: str,
    section: str,
    chunk_size=500,
    overlap=50,
):
    """Chunks text into smaller pieces with metadata."""
    words = text.split()
    chunks = []

    if not words:
        return chunks

    for i in range(0, len(words), chunk_size - overlap):
        chunk_words = words[i : i + chunk_size]
        if not chunk_words:
            break

        chunk_text = " ".join(chunk_words)

        chunk_id = f"{ticker}_{year}_{filing_type}_{section.replace(' ', '')}_{i}"

        chunks.append(
            {
                "text": chunk_text,
                "ticker": ticker,
                "year": year,
                "filing_type": filing_type,
                "section": section,
                "chunk_id": chunk_id,
            }
        )

    return chunks


if __name__ == "__main__":
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_file = PROCESSED_DIR / "chunks.jsonl"

    if out_file.exists():
        out_file.unlink()

    ticker = "AAPL"
    years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]

    print(f"Downloading filings for {ticker}...")
    html_paths = download_filings(ticker, years)

    print(f"Downloaded {len(html_paths)} filings. Extracting and chunking...")

    total_chunks = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for path in html_paths:
            filename = os.path.basename(path)
            parts = filename.replace(".html", "").split("_")
            # ticker = parts[0]
            year = int(parts[1])
            filing_type = parts[2]

            print(f"Processing {filename}...")
            sections = extract_sections(path)

            for section_name, section_text in sections.items():
                chunks = chunk_text(
                    text=section_text,
                    ticker=ticker,
                    year=year,
                    filing_type=filing_type,
                    section=section_name,
                    chunk_size=500,
                    overlap=50,
                )

                for chunk in chunks:
                    f.write(json.dumps(chunk) + "\n")
                    total_chunks += 1

    print(f"Completed! Created {total_chunks} chunks.")
