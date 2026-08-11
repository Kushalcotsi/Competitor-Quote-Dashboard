import argparse
import json
import os
from pathlib import Path
from typing import Any

from pdf2image import convert_from_path
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError
from PIL import Image, ImageDraw, ImageFont


COLORS = {
    "summary_value": "limegreen",
    "summary_label": "orange",
    "line_item_row": "red",
    "line_item_value": "dodgerblue",
}


def load_expense_json(path: str | Path) -> dict[str, Any]:
    """Load raw Textract AnalyzeExpense JSON."""
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"Expense JSON not found: {json_path}")

    with json_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def process_expense_json(expense_json: dict[str, Any]) -> dict[str, Any]:
    """Extract summary fields and line items with labels, values, and bounding boxes."""
    summary_fields = []
    line_items = []

    for wrapper_page_number, page_response in enumerate(expense_json.get("Pages", []), start=1):
        for expense_document in page_response.get("ExpenseDocuments", []):
            expense_index = expense_document.get("ExpenseIndex")

            for field in expense_document.get("SummaryFields", []):
                summary_fields.append(
                    normalize_expense_field(
                        field=field,
                        wrapper_page_number=wrapper_page_number,
                        expense_index=expense_index,
                    )
                )

            for group in expense_document.get("LineItemGroups", []):
                group_index = group.get("LineItemGroupIndex")
                for row_number, line_item in enumerate(group.get("LineItems", []), start=1):
                    normalized_fields = [
                        normalize_expense_field(
                            field=item_field,
                            wrapper_page_number=wrapper_page_number,
                            expense_index=expense_index,
                        )
                        for item_field in line_item.get("LineItemExpenseFields", [])
                    ]
                    line_items.append(
                        {
                            "expense_index": expense_index,
                            "page": field_page(normalized_fields, wrapper_page_number),
                            "line_item_group_index": group_index,
                            "row_number": row_number,
                            "fields": normalized_fields,
                            "bb": combined_bb(
                                [
                                    field.get("value_bb")
                                    for field in normalized_fields
                                    if field.get("value_bb")
                                ]
                            ),
                        }
                    )

    return {
        "source_file": expense_json.get("SourceFile"),
        "api": expense_json.get("Api", "AnalyzeExpense"),
        "page_count": expense_json.get("PageCount"),
        "summary_fields": summary_fields,
        "line_items": line_items,
    }


def normalize_expense_field(
    field: dict[str, Any],
    wrapper_page_number: int,
    expense_index: int | None,
) -> dict[str, Any]:
    """Normalize one SummaryFields or LineItemExpenseFields object."""
    field_type = field.get("Type", {})
    label = field.get("LabelDetection", {})
    value = field.get("ValueDetection", {})

    return {
        "expense_index": expense_index,
        "page": field.get("PageNumber") or wrapper_page_number,
        "field_name": field_type.get("Text"),
        "field_confidence": field_type.get("Confidence"),
        "label": label.get("Text"),
        "label_confidence": label.get("Confidence"),
        "label_bb": detection_bb(label),
        "value": value.get("Text"),
        "value_confidence": value.get("Confidence"),
        "value_bb": detection_bb(value),
        "group_properties": field.get("GroupProperties", []),
    }


def detection_bb(detection: dict[str, Any]) -> dict[str, float] | None:
    """Extract normalized bounding box from a LabelDetection or ValueDetection object."""
    bbox = detection.get("Geometry", {}).get("BoundingBox")
    if not bbox:
        return None

    return {
        "topleft_x": float(bbox.get("Left", 0.0)),
        "topleft_y": float(bbox.get("Top", 0.0)),
        "height": float(bbox.get("Height", 0.0)),
        "width": float(bbox.get("Width", 0.0)),
    }


def combined_bb(boxes: list[dict[str, float]]) -> dict[str, float] | None:
    """Combine multiple normalized boxes into one bounding box."""
    if not boxes:
        return None

    left = min(box["topleft_x"] for box in boxes)
    top = min(box["topleft_y"] for box in boxes)
    right = max(box["topleft_x"] + box["width"] for box in boxes)
    bottom = max(box["topleft_y"] + box["height"] for box in boxes)

    return {
        "topleft_x": left,
        "topleft_y": top,
        "height": bottom - top,
        "width": right - left,
    }


def field_page(fields: list[dict[str, Any]], fallback_page: int) -> int:
    """Return the first known page for a line item."""
    for field in fields:
        if field.get("page"):
            return int(field["page"])
    return fallback_page


def save_json(data: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


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
            'its bin folder with --poppler-path, for example: --poppler-path "C:\\poppler\\Library\\bin".'
        ) from exc


def draw_box(
    draw: ImageDraw.ImageDraw,
    image_size: tuple[int, int],
    bb: dict[str, float] | None,
    color: str,
    label: str,
    width: int = 3,
) -> None:
    """Draw one normalized bounding box."""
    if not bb:
        return

    image_width, image_height = image_size
    left = int(bb["topleft_x"] * image_width)
    top = int(bb["topleft_y"] * image_height)
    right = left + int(bb["width"] * image_width)
    bottom = top + int(bb["height"] * image_height)

    draw.rectangle((left, top, right, bottom), outline=color, width=width)
    label_top = max(0, top - 14)
    label_width = min(image_width - left, max(70, len(label) * 7))
    draw.rectangle((left, label_top, left + label_width, label_top + 13), fill="white")
    draw.text((left, label_top), label, fill=color, font=ImageFont.load_default())


def annotate_expense_pdf(
    processed: dict[str, Any],
    pdf_path: str | Path,
    output_dir: str | Path,
    dpi: int,
    poppler_path: str | Path | None = None,
) -> list[Path]:
    """Draw summary and line-item bounding boxes on the source PDF."""
    pages = render_pdf(pdf_path, dpi=dpi, poppler_path=poppler_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    saved_files: list[Path] = []
    annotated_pages: list[Image.Image] = []

    for page_number, page_image in enumerate(pages, start=1):
        annotated = page_image.copy()
        draw = ImageDraw.Draw(annotated)

        for item in processed.get("line_items", []):
            if item.get("page") != page_number:
                continue
            draw_box(
                draw,
                annotated.size,
                item.get("bb"),
                COLORS["line_item_row"],
                f"line item {item.get('row_number')}",
                width=5,
            )
            for field in item.get("fields", []):
                draw_box(
                    draw,
                    annotated.size,
                    field.get("value_bb"),
                    COLORS["line_item_value"],
                    str(field.get("field_name") or "item"),
                    width=2,
                )

        for field in processed.get("summary_fields", []):
            if field.get("page") != page_number:
                continue
            field_name = str(field.get("field_name") or "summary")
            draw_box(
                draw,
                annotated.size,
                field.get("label_bb"),
                COLORS["summary_label"],
                f"{field_name} label",
                width=2,
            )
            draw_box(
                draw,
                annotated.size,
                field.get("value_bb"),
                COLORS["summary_value"],
                field_name,
                width=3,
            )

        annotated_pages.append(annotated)
        page_path = output_path / f"page_{page_number}_expense_annotated.png"
        annotated.save(page_path)
        saved_files.append(page_path)

    if annotated_pages:
        pdf_output = output_path / f"{Path(pdf_path).stem}_expense_annotated.pdf"
        first_page, remaining_pages = annotated_pages[0], annotated_pages[1:]
        first_page.save(pdf_output, save_all=True, append_images=remaining_pages)
        saved_files.append(pdf_output)

    return saved_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract clean fields from Textract AnalyzeExpense JSON.")
    parser.add_argument("input_json", help="Path to expense_output.json.")
    parser.add_argument(
        "-o",
        "--output",
        default="output/textract_expense_processed.json",
        help="Path to save processed expense JSON.",
    )
    parser.add_argument("--pdf", help="Optional source PDF path for drawing bounding boxes.")
    parser.add_argument(
        "--annotate-dir",
        help="Optional output directory for annotated PDF/PNG files. Requires --pdf.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="PDF render DPI for annotations.")
    parser.add_argument(
        "--poppler-path",
        default=os.getenv("POPPLER_PATH"),
        help="Optional Poppler bin folder, e.g. C:\\poppler\\Library\\bin.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    expense_json = load_expense_json(args.input_json)
    processed = process_expense_json(expense_json)
    saved_path = save_json(processed, args.output)
    print(f"Processed expense JSON saved to: {saved_path}")

    if args.annotate_dir and not args.pdf:
        raise ValueError("--annotate-dir requires --pdf")

    if args.pdf:
        annotate_dir = args.annotate_dir or str(Path(args.output).with_suffix("")) + "_annotated"
        saved_files = annotate_expense_pdf(
            processed=processed,
            pdf_path=args.pdf,
            output_dir=annotate_dir,
            dpi=args.dpi,
            poppler_path=args.poppler_path,
        )
        print("Annotated expense files saved:")
        for saved_file in saved_files:
            print(f"- {saved_file}")


if __name__ == "__main__":
    main()
