## annotate original json

import argparse
import json
from pathlib import Path
from typing import Any

from pdf2image import convert_from_path
from PIL import Image, ImageDraw, ImageFont


ANNOTATED_TYPES = {"LINE", "TABLE"}
COLORS = {
    "LINE": "dodgerblue",
    "TABLE": "red",
}


def load_textract_json(path: str | Path) -> dict[str, Any]:
    """Load Textract JSON produced by aws_textract_ocr.py."""
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"Textract JSON not found: {json_path}")

    with json_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def resolve_pdf_path(textract_json: dict[str, Any], explicit_pdf: str | Path | None) -> Path:
    """Find the source PDF from CLI input or SourceFile metadata."""
    if explicit_pdf:
        pdf_path = Path(explicit_pdf)
    else:
        source_file = textract_json.get("SourceFile")
        if not source_file:
            raise ValueError("PDF path was not provided and SourceFile is missing in JSON.")
        pdf_path = Path("input") / source_file

    if not pdf_path.exists():
        raise FileNotFoundError(f"Source PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Source document must be a PDF: {pdf_path}")

    return pdf_path


def render_pdf_pages(pdf_path: Path, dpi: int) -> list[Image.Image]:
    """Render PDF pages to PIL images."""
    return [page.convert("RGB") for page in convert_from_path(str(pdf_path), dpi=dpi)]


def get_page_blocks(textract_json: dict[str, Any], page_index: int) -> list[dict[str, Any]]:
    """Return Textract blocks for a 0-based page index."""
    if "Pages" in textract_json:
        pages = textract_json["Pages"]
        if page_index >= len(pages):
            return []
        return pages[page_index].get("Blocks", [])

    return textract_json.get("Blocks", [])


def draw_bounding_boxes(image: Image.Image, blocks: list[dict[str, Any]]) -> Image.Image:
    """Draw LINE and TABLE bounding boxes on one page image."""
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    font = ImageFont.load_default()
    image_width, image_height = annotated.size

    # Draw tables first so line boxes remain visible if they overlap.
    blocks_to_draw = sorted(
        (block for block in blocks if block.get("BlockType") in ANNOTATED_TYPES),
        key=lambda block: 0 if block.get("BlockType") == "TABLE" else 1,
    )

    for block in blocks_to_draw:
        block_type = block["BlockType"]
        bbox = block.get("Geometry", {}).get("BoundingBox")
        if not bbox:
            continue

        left = int(bbox.get("Left", 0) * image_width)
        top = int(bbox.get("Top", 0) * image_height)
        width = int(bbox.get("Width", 0) * image_width)
        height = int(bbox.get("Height", 0) * image_height)
        right = left + width
        bottom = top + height

        color = COLORS[block_type]
        line_width = 5 if block_type == "TABLE" else 2
        draw.rectangle((left, top, right, bottom), outline=color, width=line_width)

        label = block_type
        if block_type == "LINE" and block.get("Text"):
            label = f"LINE: {block['Text'][:40]}"

        label_top = max(0, top - 14)
        draw.rectangle((left, label_top, min(image_width, left + len(label) * 7), label_top + 12), fill="white")
        draw.text((left, label_top), label, fill=color, font=font)

    return annotated


def annotate_pdf(
    textract_json_path: str | Path,
    pdf_path: str | Path | None,
    output_dir: str | Path,
    dpi: int,
) -> list[Path]:
    """Create annotated PNG pages and a combined annotated PDF."""
    textract_json = load_textract_json(textract_json_path)
    source_pdf = resolve_pdf_path(textract_json, pdf_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    rendered_pages = render_pdf_pages(source_pdf, dpi)
    annotated_pages = []
    saved_files = []

    for page_index, page_image in enumerate(rendered_pages):
        blocks = get_page_blocks(textract_json, page_index)
        annotated_page = draw_bounding_boxes(page_image, blocks)
        annotated_pages.append(annotated_page)

        png_path = output_path / f"page_{page_index + 1}_annotated.png"
        annotated_page.save(png_path)
        saved_files.append(png_path)

    if annotated_pages:
        pdf_output = output_path / f"{source_pdf.stem}_annotated.pdf"
        first_page, remaining_pages = annotated_pages[0], annotated_pages[1:]
        first_page.save(pdf_output, save_all=True, append_images=remaining_pages)
        saved_files.append(pdf_output)

    return saved_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draw Textract LINE and TABLE boxes on a source PDF.")
    parser.add_argument("textract_json", help="Path to Textract output.json.")
    parser.add_argument("--pdf", help="Optional source PDF path. Defaults to input/<SourceFile> from JSON.")
    parser.add_argument("-o", "--output-dir", default="output/textract_annotated", help="Output directory.")
    parser.add_argument("--dpi", type=int, default=300, help="PDF render DPI.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    saved_files = annotate_pdf(
        textract_json_path=args.textract_json,
        pdf_path=args.pdf,
        output_dir=args.output_dir,
        dpi=args.dpi,
    )

    print("Annotated files saved:")
    for saved_file in saved_files:
        print(f"- {saved_file}")


if __name__ == "__main__":
    main()
