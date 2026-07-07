from pathlib import Path
from shutil import copyfile

from huggingface_hub import hf_hub_download, list_repo_files


REPO_ID = "jngb-labs/InvoiceBenchmark"
REPO_TYPE = "dataset"

PDF_PREFIX = "output/pdf/"
GROUND_TRUTH_PREFIX = "output/ground_truth/"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_DIR = PROJECT_ROOT / "data" / "input"
GROUND_TRUTH_DIR = PROJECT_ROOT / "data" / "ground_truth"


def download_files(
    repo_files: list[str],
    prefix: str,
    output_dir: Path,
    label: str,
) -> int:
    files = sorted(
        path
        for path in repo_files
        if path.startswith(prefix)
        and path.lower().endswith(".pdf" if label == "PDF" else ".json")
    )

    if not files:
        raise RuntimeError(
            f"No {label} files found under {prefix!r}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nFound {len(files)} {label} files.")

    downloaded = 0

    for index, repo_path in enumerate(files, start=1):
        filename = Path(repo_path).name
        destination = output_dir / filename

        if destination.exists():
            print(
                f"[{index}/{len(files)}] "
                f"Already exists: {filename}"
            )
            continue

        print(
            f"[{index}/{len(files)}] "
            f"Downloading {filename}"
        )

        cached_path = hf_hub_download(
            repo_id=REPO_ID,
            repo_type=REPO_TYPE,
            filename=repo_path,
        )

        copyfile(cached_path, destination)
        downloaded += 1

    return downloaded


def main() -> None:
    print(f"Dataset: {REPO_ID}")
    print("Listing repository files...")

    repo_files = list_repo_files(
        repo_id=REPO_ID,
        repo_type=REPO_TYPE,
    )

    pdf_downloaded = download_files(
        repo_files=repo_files,
        prefix=PDF_PREFIX,
        output_dir=INPUT_DIR,
        label="PDF",
    )

    ground_truth_downloaded = download_files(
        repo_files=repo_files,
        prefix=GROUND_TRUTH_PREFIX,
        output_dir=GROUND_TRUTH_DIR,
        label="JSON",
    )

    print("\nDataset preparation complete.")
    print(f"PDFs downloaded: {pdf_downloaded}")
    print(f"Ground-truth files downloaded: {ground_truth_downloaded}")
    print(f"Input directory: {INPUT_DIR}")
    print(f"Ground-truth directory: {GROUND_TRUTH_DIR}")


if __name__ == "__main__":
    main()