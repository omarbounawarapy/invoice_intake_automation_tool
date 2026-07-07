from pathlib import Path

from huggingface_hub import list_repo_files, hf_hub_download

REPO_ID = "jngb-labs/InvoiceBenchmark"
REPO_TYPE = "dataset"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "input"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Listing files from {REPO_ID}...")

    files = list_repo_files(
        repo_id=REPO_ID,
        repo_type=REPO_TYPE,
    )

    pdf_files = sorted(
        path
        for path in files
        if path.startswith("output/pdf/")
        and path.lower().endswith(".pdf")
    )

    if not pdf_files:
        raise RuntimeError("No PDF files found in output/pdf/")

    print(f"Found {len(pdf_files)} PDF invoices.")

    for index, repo_path in enumerate(pdf_files, start=1):
        filename = Path(repo_path).name
        destination = OUTPUT_DIR / filename

        if destination.exists():
            print(f"[{index}/{len(pdf_files)}] Already exists: {filename}")
            continue

        print(f"[{index}/{len(pdf_files)}] Downloading: {filename}")

        downloaded_path = hf_hub_download(
            repo_id=REPO_ID,
            repo_type=REPO_TYPE,
            filename=repo_path,
        )

        destination.write_bytes(Path(downloaded_path).read_bytes())

    print()
    print(f"Downloaded dataset to: {OUTPUT_DIR}")
    print(f"PDF invoices available: {len(pdf_files)}")


if __name__ == "__main__":
    main()