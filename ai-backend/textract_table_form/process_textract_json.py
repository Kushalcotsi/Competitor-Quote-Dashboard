# convert textract json to line and table blocks for downstream use
import argparse
import html
import json
from pathlib import Path
from typing import Any


TABLE_RELATED_TYPES = {"TABLE", "CELL", "MERGED_CELL", "TABLE_TITLE", "TABLE_SUMMARY"}


def load_textract_json(path: str | Path) -> dict[str, Any]:
    """Load raw Textract JSON saved by aws_textract_ocr.py."""
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"Textract JSON not found: {json_path}")

    with json_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def process_textract_json(textract_json: dict[str, Any]) -> dict[str, Any]:
    """Convert raw Textract JSON into line/table blocks for downstream use."""
    output_blocks: dict[str, dict[str, Any]] = {}
    block_counter = 1

    for page_number, page in enumerate(iter_pages(textract_json), start=1):
        blocks = page.get("Blocks", [])
        block_map = {block["Id"]: block for block in blocks if "Id" in block}
        tables = [block for block in blocks if block.get("BlockType") == "TABLE"]
        table_boxes = [to_bb(table) for table in tables]

        candidates: list[dict[str, Any]] = []

        for line in blocks:
            if line.get("BlockType") != "LINE":
                continue

            line_bb = to_bb(line)
            if not line_bb:
                continue

            centroid = get_centroid(line_bb)
            if any(point_inside_bb(centroid, table_bb) for table_bb in table_boxes):
                continue

            candidates.append(
                {
                    "type": "line",
                    "page": page_number,
                    "text": line.get("Text", ""),
                    "bb": line_bb,
                    "_sort": sort_key(line_bb),
                }
            )

        for table in tables:
            table_bb = to_bb(table)
            if not table_bb:
                continue

            table_words = words_inside_table(blocks, table_bb)
            candidates.append(
                {
                    "type": "table",
                    "page": page_number,
                    "text": table_to_html(table, block_map),
                    "bb": table_bb,
                    "table_src": table_words,
                    "_sort": sort_key(table_bb),
                }
            )

        for block in sorted(candidates, key=lambda item: item["_sort"]):
            block.pop("_sort", None)
            output_blocks[f"src_{block_counter}"] = block
            block_counter += 1

    return {"blocks": output_blocks}


def iter_pages(textract_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Support both wrapper format and single raw Textract response format."""
    if "Pages" in textract_json:
        return textract_json["Pages"]
    return [textract_json]


def words_inside_table(blocks: list[dict[str, Any]], table_bb: dict[str, float]) -> list[dict[str, Any]]:
    """Include every WORD block whose centroid lies inside the table bbox."""
    words = []
    for block in blocks:
        if block.get("BlockType") != "WORD":
            continue

        word_bb = to_bb(block)
        if not word_bb:
            continue

        if point_inside_bb(get_centroid(word_bb), table_bb):
            words.append(
                {
                    "text": block.get("Text", ""),
                    "bb": word_bb,
                }
            )

    return sorted(words, key=lambda word: sort_key(word["bb"]))


def table_to_html(table: dict[str, Any], block_map: dict[str, dict[str, Any]]) -> str:
    """Convert Textract CELL, MERGED_CELL, title, and summary blocks to HTML."""
    title = relationship_text(table, block_map, "TABLE_TITLE")
    summary = relationship_text(table, block_map, "TABLE_SUMMARY")
    cells = relationship_blocks(table, block_map, "CHILD", {"CELL"})
    merged_cells = relationship_blocks(table, block_map, "MERGED_CELL", {"MERGED_CELL"})

    html_parts = ['<div class="textract-table-block">']

    if title:
        html_parts.append(f'  <div class="table-title">{html.escape(title)}</div>')

    if summary:
        html_parts.append(f'  <div class="table-summary">{html.escape(summary)}</div>')

    html_parts.append(cells_to_html_table(cells, block_map))

    merged_html = merged_cells_to_html(merged_cells, block_map)
    if merged_html:
        html_parts.append(merged_html)

    html_parts.append("</div>")
    return "\n".join(part for part in html_parts if part).strip()


def cells_to_html_table(cells: list[dict[str, Any]], block_map: dict[str, dict[str, Any]]) -> str:
    """Create an HTML table from Textract CELL blocks."""
    if not cells:
        return "  <table></table>"

    max_row = max(cell.get("RowIndex", 1) + cell.get("RowSpan", 1) - 1 for cell in cells)
    rows_by_index: dict[int, list[dict[str, Any]]] = {row_index: [] for row_index in range(1, max_row + 1)}

    for cell in cells:
        rows_by_index.setdefault(cell.get("RowIndex", 1), []).append(cell)

    html_rows = ["  <table>"]
    for row_index in sorted(rows_by_index):
        html_rows.append("    <tr>")
        for cell in sorted(rows_by_index[row_index], key=lambda item: item.get("ColumnIndex", 1)):
            text = html.escape(block_text(cell, block_map))
            rowspan = cell.get("RowSpan", 1)
            colspan = cell.get("ColumnSpan", 1)
            span_attrs = []
            if rowspan > 1:
                span_attrs.append(f'rowspan="{rowspan}"')
            if colspan > 1:
                span_attrs.append(f'colspan="{colspan}"')
            attrs = " " + " ".join(span_attrs) if span_attrs else ""
            html_rows.append(f"      <td{attrs}>{text}</td>")
        html_rows.append("    </tr>")
    html_rows.append("  </table>")
    return "\n".join(html_rows)


def merged_cells_to_html(
    merged_cells: list[dict[str, Any]],
    block_map: dict[str, dict[str, Any]],
) -> str:
    """Summarize merged cells as HTML metadata."""
    if not merged_cells:
        return ""

    lines = ['  <div class="merged-cells">', "    <strong>Merged Cells:</strong>", "    <ul>"]
    for merged_cell in merged_cells:
        text = html.escape(block_text(merged_cell, block_map))
        lines.append(
            "      <li "
            f'data-row="{merged_cell.get("RowIndex")}" '
            f'data-col="{merged_cell.get("ColumnIndex")}" '
            f'data-rowspan="{merged_cell.get("RowSpan")}" '
            f'data-colspan="{merged_cell.get("ColumnSpan")}">'
            f"{text}</li>"
        )
    lines.extend(["    </ul>", "  </div>"])
    return "\n".join(lines)


def relationship_blocks(
    block: dict[str, Any],
    block_map: dict[str, dict[str, Any]],
    relationship_type: str,
    block_types: set[str],
) -> list[dict[str, Any]]:
    """Return related blocks matching a relationship type and block type set."""
    related = []
    for relationship in block.get("Relationships", []):
        if relationship.get("Type") != relationship_type:
            continue
        for block_id in relationship.get("Ids", []):
            child = block_map.get(block_id)
            if child and child.get("BlockType") in block_types:
                related.append(child)
    return related


def relationship_text(
    block: dict[str, Any],
    block_map: dict[str, dict[str, Any]],
    relationship_type: str,
) -> str:
    """Collect text from related title or summary blocks."""
    related = relationship_blocks(block, block_map, relationship_type, {relationship_type})
    return " ".join(block_text(item, block_map) for item in related).strip()


def block_text(block: dict[str, Any], block_map: dict[str, dict[str, Any]]) -> str:
    """Get direct Text or collect child WORD text for a Textract block."""
    if block.get("Text"):
        return block["Text"].strip()

    parts = []
    for relationship in block.get("Relationships", []):
        if relationship.get("Type") != "CHILD":
            continue
        for block_id in relationship.get("Ids", []):
            child = block_map.get(block_id)
            if not child:
                continue
            if child.get("BlockType") == "WORD":
                parts.append(child.get("Text", ""))
            elif child.get("BlockType") == "SELECTION_ELEMENT":
                if child.get("SelectionStatus") == "SELECTED":
                    parts.append("[X]")
    return " ".join(parts).strip()


def to_bb(block: dict[str, Any]) -> dict[str, float] | None:
    """Convert Textract normalized bbox into requested top-left/height/width shape."""
    bbox = block.get("Geometry", {}).get("BoundingBox")
    if not bbox:
        return None

    return {
        "topleft_x": float(bbox.get("Left", 0.0)),
        "topleft_y": float(bbox.get("Top", 0.0)),
        "height": float(bbox.get("Height", 0.0)),
        "width": float(bbox.get("Width", 0.0)),
    }


def get_centroid(bb: dict[str, float]) -> tuple[float, float]:
    """Calculate centroid from top-left and bottom-right coordinates."""
    topleft_x = bb["topleft_x"]
    topleft_y = bb["topleft_y"]
    bottomright_x = topleft_x + bb["width"]
    bottomright_y = topleft_y + bb["height"]
    return (topleft_x + bottomright_x) / 2, (topleft_y + bottomright_y) / 2


def point_inside_bb(point: tuple[float, float], bb: dict[str, float]) -> bool:
    x, y = point
    left = bb["topleft_x"]
    top = bb["topleft_y"]
    right = left + bb["width"]
    bottom = top + bb["height"]
    return left <= x <= right and top <= y <= bottom


def sort_key(bb: dict[str, float]) -> tuple[float, float]:
    return bb["topleft_y"], bb["topleft_x"]


def save_json(data: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post-process raw AWS Textract JSON.")
    parser.add_argument("input_json", help="Path to raw Textract output.json.")
    parser.add_argument(
        "-o",
        "--output",
        default="output/textract_processed.json",
        help="Path to save processed JSON.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    textract_json = load_textract_json(args.input_json)
    processed = process_textract_json(textract_json)
    saved_path = save_json(processed, args.output)
    print(f"Processed Textract JSON saved to: {saved_path}")


if __name__ == "__main__":
    main()
