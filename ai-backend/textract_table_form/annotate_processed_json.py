## annotate processed json

import argparse
import json
import os
from pathlib import Path
from typing import Any

from pdf2image import convert_from_path
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError
from PIL import Image, ImageDraw, ImageFont


COLORS = {
    "line": "dodgerblue",
    "table": "red",
}


def load_processed_json(path: str | Path) -> dict[str, Any]:
    """Load processed JSON created by process_textract_json.py."""
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"Processed JSON not found: {json_path}")

    with json_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def render_pdf(pdf_path: str | Path, dpi: int, poppler_path: str | Path | None = None) -> list[Image.Image]:
    """Render source PDF pages as RGB images."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"Source PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Source file must be a PDF: {path}")

    try:
        return [
            page.convert("RGB")
            for page in convert_from_path(
                str(path),
                dpi=dpi,
                poppler_path=str(poppler_path) if poppler_path else None,
            )
        ]
    except (PDFInfoNotInstalledError, PDFPageCountError) as exc:
        raise RuntimeError(
            "Could not render the PDF with pdf2image. Install Poppler for Windows and pass "
            'its bin folder with --poppler-path, for example: --poppler-path "C:\\poppler\\Library\\bin". '
            "This is needed when another program, such as MiKTeX, shadows Poppler's pdfinfo.exe."
        ) from exc


def blocks_by_page(processed_json: dict[str, Any]) -> dict[int, list[tuple[str, dict[str, Any]]]]:
    """Group line/table blocks by page number."""
    grouped: dict[int, list[tuple[str, dict[str, Any]]]] = {}
    for block_id, block in processed_json.get("blocks", {}).items():
        block_type = block.get("type")
        if block_type not in COLORS:
            continue
        page_number = int(block.get("page", 1))
        grouped.setdefault(page_number, []).append((block_id, block))
    return grouped


def draw_blocks(
    image: Image.Image,
    page_blocks: list[tuple[str, dict[str, Any]]],
) -> Image.Image:
    """Draw processed line/table bounding boxes on one page image."""
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    font = ImageFont.load_default()
    image_width, image_height = annotated.size

    # Draw tables first, then lines, so line boxes remain visible.
    ordered_blocks = sorted(
        page_blocks,
        key=lambda item: 0 if item[1].get("type") == "table" else 1,
    )

    for block_id, block in ordered_blocks:
        bb = block.get("bb")
        if not bb:
            continue

        left = int(bb["topleft_x"] * image_width)
        top = int(bb["topleft_y"] * image_height)
        width = int(bb["width"] * image_width)
        height = int(bb["height"] * image_height)
        right = left + width
        bottom = top + height

        block_type = block["type"]
        color = COLORS[block_type]
        line_width = 5 if block_type == "table" else 2
        draw.rectangle((left, top, right, bottom), outline=color, width=line_width)

        label = f"{block_id}: {block_type}"
        if block_type == "line" and block.get("text"):
            label = f"{block_id}: {block['text'][:35]}"

        label_top = max(0, top - 14)
        label_width = min(image_width - left, max(60, len(label) * 7))
        draw.rectangle((left, label_top, left + label_width, label_top + 13), fill="white")
        draw.text((left, label_top), label, fill=color, font=font)

    return annotated


def annotate_processed_json(
    processed_json_path: str | Path,
    pdf_path: str | Path,
    output_dir: str | Path,
    dpi: int,
    poppler_path: str | Path | None = None,
) -> list[Path]:
    """Create annotated PNG pages and a combined PDF from processed JSON."""
    processed_json = load_processed_json(processed_json_path)
    rendered_pages = render_pdf(pdf_path, dpi, poppler_path=poppler_path)
    grouped_blocks = blocks_by_page(processed_json)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    annotated_pages = []
    saved_files = []

    for page_index, page_image in enumerate(rendered_pages, start=1):
        annotated_page = draw_blocks(page_image, grouped_blocks.get(page_index, []))
        annotated_pages.append(annotated_page)

        png_path = output_path / f"page_{page_index}_processed_annotated.png"
        annotated_page.save(png_path)
        saved_files.append(png_path)

    if annotated_pages:
        pdf_stem = Path(pdf_path).stem
        pdf_output = output_path / f"{pdf_stem}_processed_annotated.pdf"
        first_page, remaining_pages = annotated_pages[0], annotated_pages[1:]
        first_page.save(pdf_output, save_all=True, append_images=remaining_pages)
        saved_files.append(pdf_output)

    return saved_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draw line/table boxes from processed Textract JSON.")
    parser.add_argument("processed_json", help="Path to processed_output_html.json.")
    parser.add_argument("--pdf", required=True, help="Source PDF path.")
    parser.add_argument("-o", "--output-dir", default="output/processed_annotated", help="Output directory.")
    parser.add_argument("--dpi", type=int, default=300, help="PDF render DPI.")
    parser.add_argument(
        "--poppler-path",
        default=os.getenv("POPPLER_PATH"),
        help="Optional Poppler bin folder, e.g. C:\\poppler\\Library\\bin.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    saved_files = annotate_processed_json(
        processed_json_path=args.processed_json,
        pdf_path=args.pdf,
        output_dir=args.output_dir,
        dpi=args.dpi,
        poppler_path=args.poppler_path,
    )

    print("Annotated files saved:")
    for saved_file in saved_files:
        print(f"- {saved_file}")


if __name__ == "__main__":
    main()
