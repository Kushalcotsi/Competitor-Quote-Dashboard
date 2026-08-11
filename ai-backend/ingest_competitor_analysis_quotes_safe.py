import hashlib
import json
import re
from pathlib import Path
from typing import Any

import ingest_competitor_quote_expenses as pipeline
import ingest_competitor_quotes as quote_writer


def safe_name(value: str) -> str:
    """Return a filesystem-safe name for generated output paths."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip().rstrip(".")
    if cleaned:
        return cleaned[:120]
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def safe_output_dir(original_output_dir: Path) -> Path:
    """Return a sanitized Textract output directory path."""
    return original_output_dir.parent / safe_name(original_output_dir.name)


def process_document_safe(input_path: Path, output_dir: Path, region: str | None, dpi: int) -> dict[str, Any]:
    """Run Textract with a sanitized output directory."""
    return pipeline.process_document_original(
        input_path=input_path,
        output_dir=safe_output_dir(output_dir),
        region=region,
        dpi=dpi,
    )


def save_raw_response_safe(result: dict[str, Any], source_pdf: Path, output_root: Path) -> Path:
    """Save a raw Textract response under a sanitized folder name."""
    target_dir = output_root / safe_name(source_pdf.stem)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "expense_output.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return target


def main() -> None:
    """Run quote ingestion with safe output path handling."""
    pipeline.POSTGRES_DB = "competitor_analysis"
    pipeline.postgres_upsert = quote_writer.postgres_upsert
    pipeline.process_document_original = pipeline.process_document
    pipeline.process_document = process_document_safe
    pipeline.save_raw_response = save_raw_response_safe
    pipeline.main()


if __name__ == "__main__":
    main()
