import argparse
from io import BytesIO
import json
import os
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError
from pdf2image import convert_from_path


SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def load_env_file(env_path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE pairs from a .env file without extra dependencies."""
    path = Path(env_path)
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def analyze_expense_bytes(textract_client: Any, document_bytes: bytes) -> dict[str, Any]:
    """Send image bytes directly to Textract AnalyzeExpense."""
    return textract_client.analyze_expense(Document={"Bytes": document_bytes})


def analyze_image_file(textract_client: Any, file_path: Path) -> dict[str, Any]:
    """Send a local PNG/JPG/JPEG file directly to AnalyzeExpense."""
    with file_path.open("rb") as file:
        return analyze_expense_bytes(textract_client, file.read())


def analyze_pdf_as_images(textract_client: Any, file_path: Path, dpi: int = 300) -> list[dict[str, Any]]:
    """Convert each PDF page to PNG bytes and send each page to AnalyzeExpense."""
    pages = convert_from_path(str(file_path), dpi=dpi)
    responses = []

    for page_number, page in enumerate(pages, start=1):
        image_buffer = BytesIO()
        page.convert("RGB").save(image_buffer, format="PNG")
        response = analyze_expense_bytes(textract_client, image_buffer.getvalue())
        response["PageNumber"] = page_number
        responses.append(response)

    return responses


def save_response(expense_response: dict[str, Any], output_dir: Path) -> Path:
    """Save the raw AnalyzeExpense response as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "expense_output.json"
    output_path.write_text(
        json.dumps(expense_response, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return output_path


def process_document(
    input_path: Path,
    output_dir: Path,
    region: str | None,
    dpi: int,
) -> dict[str, Any]:
    """Run AWS Textract AnalyzeExpense and save the raw response."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {input_path.suffix}")

    session = boto3.Session(region_name=region)
    textract_client = session.client("textract")

    try:
        if input_path.suffix.lower() == ".pdf":
            page_responses = analyze_pdf_as_images(textract_client, input_path, dpi=dpi)
        else:
            page_responses = [analyze_image_file(textract_client, input_path)]
    except ClientError as error:
        raise RuntimeError(f"AWS Textract AnalyzeExpense failed: {error}") from error

    result = {
        "SourceFile": input_path.name,
        "Api": "AnalyzeExpense",
        "PageCount": len(page_responses),
        "Pages": page_responses,
    }
    save_response(result, output_dir)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Expense extraction using AWS Textract AnalyzeExpense.")
    parser.add_argument("input", help="Path to a PDF, PNG, JPG, or JPEG document.")
    parser.add_argument("-o", "--output-dir", default="textract_expense_output", help="Output directory.")
    parser.add_argument("--env-file", default=".env", help="Optional .env file to load.")
    parser.add_argument("--region", help="AWS region, e.g. us-east-1.")
    parser.add_argument("--dpi", type=int, default=300, help="PDF render DPI before Textract.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    load_env_file(args.env_file)

    process_document(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir),
        region=args.region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
        dpi=args.dpi,
    )
    print(f"Saved AnalyzeExpense response to: {(Path(args.output_dir) / 'expense_output.json').resolve()}")


if __name__ == "__main__":
    main()
