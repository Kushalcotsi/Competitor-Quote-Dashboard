import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


TEXTRACT_SCRIPT_DIR = Path(__file__).resolve().parent / "output" / "textract_inv2_expense"
if str(TEXTRACT_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(TEXTRACT_SCRIPT_DIR))

from textract_expenseAPI.aws_textract_expense import load_env_file, process_document 

DEFAULT_SOURCE_DIR = Path(r"D:\willscot-competitor-analysis\Competitor Quotes")
DEFAULT_OUTPUT_DIR = Path("output") / "competitor_quotes_expense"
DEFAULT_SQLITE_PATH = Path("quotes_replica.sqlite3")
POSTGRES_HOST = "ai-test-quotes-database-1.ci34282eytrl.us-east-1.rds.amazonaws.com"
POSTGRES_PORT = 5432
POSTGRES_USER = "postgres"
POSTGRES_DB = "postgres"

QUOTE_STATUS = {"Draft", "Accepted", "Rejected", "Expired"}
PROPOSAL_TYPES = {"Quote", "Bid", "Lease Proposal", "Rental Quote"}
BILLING_CYCLES = {"Daily", "Weekly", "Monthly", "28-Day", "4 Week"}
VAP_KEYWORDS = {
    "waiver",
    "protection",
    "insurance",
    "service",
    "fee",
    "environmental",
    "fuel",
}


@dataclass
class ParsedQuote:
    """Structured quote data ready for database persistence."""
    company: dict[str, Any]
    client: dict[str, Any]
    quote: dict[str, Any]
    line_items: list[dict[str, Any]]
    vap_services: list[dict[str, Any]]

def parse_money(value: Any) -> Decimal:
    """Convert a Textract or text money value into a Decimal amount."""
    if value is None:
        return Decimal("0")
    text = str(value).strip()
    if not text:
        return Decimal("0")
    negative = text.startswith("(") and text.endswith(")")
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text or text in {"-", ".", "-."}:
        return Decimal("0")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return Decimal("0")
    return -amount if negative else amount


def parse_int(value: Any, default: int = 1) -> int:
    """Extract the first integer from a value, falling back to a default."""
    text = "" if value is None else str(value)
    match = re.search(r"-?\d+", text.replace(",", ""))
    if not match:
        return default
    return int(match.group(0))


def parse_date(value: Any) -> date | None:
    """Parse common invoice date formats into a date."""
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    match = re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", text)
    if match:
        return parse_date(match.group(0))
    return None


def text_value(field: dict[str, Any]) -> str:
    """Return the trimmed text value from a Textract field."""
    return str(field.get("ValueDetection", {}).get("Text") or "").strip()


def field_type(field: dict[str, Any]) -> str:
    """Return the normalized Textract field type."""
    return str(field.get("Type", {}).get("Text") or "").strip().upper()


def group_roles(field: dict[str, Any]) -> set[str]:
    """Return the normalized group roles attached to a Textract field."""
    roles: set[str] = set()
    for group in field.get("GroupProperties", []) or []:
        roles.update(str(role).upper() for role in group.get("Types", []) or [])
    return roles


def collect_summary_fields(expense_response: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect all summary fields from a Textract AnalyzeExpense response."""
    fields = []
    for page in expense_response.get("Pages", []):
        for expense_doc in page.get("ExpenseDocuments", []):
            fields.extend(expense_doc.get("SummaryFields", []))
    return fields


def first_summary(summary: list[dict[str, Any]], *types: str, role: str | None = None) -> str:
    """Return the first non-empty summary value matching one of the field types."""
    wanted = {item.upper() for item in types}
    role_upper = role.upper() if role else None
    for field in summary:
        if field_type(field) not in wanted:
            continue
        if role_upper and role_upper not in group_roles(field):
            continue
        value = text_value(field)
        if value:
            return value
    return ""


def all_summary(summary: list[dict[str, Any]], *types: str) -> list[str]:
    """Return unique non-empty summary values matching the field types."""
    wanted = {item.upper() for item in types}
    values = []
    for field in summary:
        if field_type(field) in wanted:
            value = text_value(field)
            if value and value not in values:
                values.append(value)
    return values


def split_city_state_zip(address: str) -> tuple[str, str, str]:
    """Split the last address line into city, state, and ZIP when possible."""
    lines = [line.strip() for line in address.splitlines() if line.strip()]
    tail = lines[-1] if lines else ""
    match = re.search(r"([A-Za-z .'-]+)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)", tail)
    if not match:
        return "", "", ""
    return match.group(1).strip(), match.group(2), match.group(3)


def clean_quote_number(value: str, source_file: str) -> str:
    """Normalize a quote number or generate a deterministic fallback from the source file."""
    text = value.strip().lstrip("#").strip()
    if text:
        return re.sub(r"\s+", "-", text)[:100]
    digest = hashlib.sha1(source_file.encode("utf-8")).hexdigest()[:12]
    return f"AUTO-{Path(source_file).stem[:70]}-{digest}"[:100]


def normalize_proposal_type(text: str) -> str:
    """Infer a supported proposal type from free text."""
    lowered = text.lower()
    if "bid" in lowered:
        return "Bid"
    if "lease" in lowered:
        return "Lease Proposal"
    if "rental" in lowered:
        return "Rental Quote"
    return "Quote"


def normalize_billing_cycle(label: str, text: str = "") -> str | None:
    """Infer a supported billing cycle from labels and product text."""
    joined = f"{label} {text}".lower()
    if "28" in joined and "day" in joined:
        return "28-Day"
    if "4" in joined and "week" in joined:
        return "4 Week"
    if "month" in joined:
        return "Monthly"
    if "week" in joined:
        return "Weekly"
    if "day" in joined or "daily" in joined:
        return "Daily"
    return None


def line_field_map(line_item: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """Group Textract line-item fields by normalized field type."""
    grouped: dict[str, list[dict[str, str]]] = {}
    for field in line_item.get("LineItemExpenseFields", []):
        kind = field_type(field)
        value = text_value(field)
        label = str(field.get("LabelDetection", {}).get("Text") or "").strip()
        if value or label:
            grouped.setdefault(kind, []).append({"value": value, "label": label})
    return grouped


def first_line_value(fields: dict[str, list[dict[str, str]]], *types: str) -> str:
    """Return the first non-empty value from grouped line-item fields."""
    for kind in types:
        for candidate in fields.get(kind.upper(), []):
            if candidate["value"]:
                return candidate["value"]
    return ""


def infer_product_name(fields: dict[str, list[dict[str, str]]]) -> str:
    """Choose the best available product name from line-item fields."""
    for kind in ("ITEM", "PRODUCT_CODE", "EXPENSE_ROW", "OTHER"):
        value = first_line_value(fields, kind)
        if value:
            return value
    return "Unspecified line item"


def classify_service(product_name: str) -> str | None:
    """Classify a product name as a service category when keywords match."""
    lowered = product_name.lower()
    if "delivery" in lowered or "deliver" in lowered or "freight" in lowered:
        return "delivery"
    if "pickup" in lowered or "pick up" in lowered or "return" in lowered:
        return "pickup"
    if "setup" in lowered or "set up" in lowered or "install" in lowered:
        return "setup"
    if "teardown" in lowered or "tear down" in lowered or "dismantle" in lowered:
        return "teardown"
    if any(keyword in lowered for keyword in VAP_KEYWORDS):
        return "vap"
    return None


def collect_line_items(expense_response: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect all line items from a Textract AnalyzeExpense response."""
    rows = []
    for page in expense_response.get("Pages", []):
        for expense_doc in page.get("ExpenseDocuments", []):
            for group in expense_doc.get("LineItemGroups", []):
                rows.extend(group.get("LineItems", []))
    return rows


def parse_quote(expense_response: dict[str, Any], source_pdf: Path) -> ParsedQuote:
    """Transform a Textract AnalyzeExpense response into normalized quote records."""
    summary = collect_summary_fields(expense_response)
    vendor_address = first_summary(summary, "VENDOR_ADDRESS", "ADDRESS", role="VENDOR")
    receiver_address = first_summary(summary, "RECEIVER_ADDRESS", "ADDRESS", role="RECEIVER")
    vendor_city, vendor_state, _ = split_city_state_zip(vendor_address)
    client_city, client_state, client_zip = split_city_state_zip(receiver_address)

    company_name = first_summary(summary, "VENDOR_NAME", "NAME", role="VENDOR") or "Unknown Vendor"
    client_name = first_summary(summary, "RECEIVER_NAME", "NAME", role="RECEIVER") or "Unknown Client"
    quote_number = clean_quote_number(first_summary(summary, "INVOICE_RECEIPT_ID", "QUOTE_NUMBER"), source_pdf.name)
    quote_date = (
        parse_date(first_summary(summary, "INVOICE_RECEIPT_DATE", "QUOTE_DATE", "ORDER_DATE"))
        or parse_date(next((value for value in all_summary(summary, "OTHER") if parse_date(value)), ""))
        or date.today()
    )
    expiration_date = parse_date(first_summary(summary, "DUE_DATE", "EXPIRATION_DATE"))
    subtotal = parse_money(first_summary(summary, "SUBTOTAL"))
    tax = parse_money(first_summary(summary, "TAX"))
    grand_total = parse_money(first_summary(summary, "TOTAL", "AMOUNT_DUE"))
    if grand_total == 0:
        grand_total = subtotal + tax

    line_items: list[dict[str, Any]] = []
    vap_services: list[dict[str, Any]] = []
    service_totals = {"delivery": Decimal("0"), "pickup": Decimal("0"), "setup": Decimal("0"), "teardown": Decimal("0")}
    vap_total = Decimal("0")

    for raw_line in collect_line_items(expense_response):
        fields = line_field_map(raw_line)
        product_name = infer_product_name(fields)
        quantity = parse_int(first_line_value(fields, "QUANTITY"), default=1)
        extended_price = parse_money(first_line_value(fields, "PRICE", "AMOUNT"))
        billing_label = " ".join(
            item["label"] for values in fields.values() for item in values if item.get("label")
        )
        billing_cycle = normalize_billing_cycle(billing_label, product_name)
        proposal_type = normalize_proposal_type(" ".join(all_summary(summary, "OTHER")) + " " + product_name)
        remarks = first_line_value(fields, "EXPENSE_ROW")
        service_type = classify_service(product_name)

        row = {
            "category": service_type or "Equipment",
            "subcategory": first_line_value(fields, "PRODUCT_CODE") or None,
            "product_name": product_name[:255],
            "product_type": None,
            "proposal_type": proposal_type if proposal_type in PROPOSAL_TYPES else None,
            "billing_cycle": billing_cycle if billing_cycle in BILLING_CYCLES else None,
            "size": None,
            "dimensions": None,
            "quantity": quantity,
            "extended_price": extended_price,
            "is_recurring": billing_cycle is not None,
            "is_rental": service_type is None,
            "remarks": remarks or None,
        }
        if service_type in service_totals:
            service_totals[service_type] += extended_price
        if service_type == "vap":
            vap_total += extended_price
            vap_services.append(
                {
                    "vap_name": product_name[:255],
                    "category": "VAP",
                    "proposal_type": row["proposal_type"],
                    "billing_cycle": row["billing_cycle"],
                    "quantity": quantity,
                    "extended_price": extended_price,
                    "is_recurring": row["is_recurring"],
                    "is_rental": False,
                    "remarks": remarks or None,
                }
            )
        elif service_type in service_totals:
            vap_services.append(
                {
                    "vap_name": product_name[:255],
                    "category": service_type.title(),
                    "proposal_type": row["proposal_type"],
                    "billing_cycle": row["billing_cycle"],
                    "quantity": quantity,
                    "extended_price": extended_price,
                    "is_recurring": row["is_recurring"],
                    "is_rental": False,
                    "remarks": remarks or None,
                }
            )
        else:
            line_items.append(row)

    return ParsedQuote(
        company={
            "company_name": company_name[:255],
            "website": first_summary(summary, "VENDOR_URL")[:500] or None,
            "headquarters_city": vendor_city or None,
            "headquarters_state": vendor_state or None,
            "notes": vendor_address or None,
        },
        client={
            "client_name": client_name[:255],
            "industry": None,
            "contact_name": None,
            "contact_phone": first_summary(summary, "RECEIVER_PHONE")[:30] or None,
            "contact_email": first_summary(summary, "RECEIVER_EMAIL")[:255] or None,
            "billing_address": receiver_address or None,
            "city": client_city or None,
            "state": client_state or None,
            "zip_code": client_zip or None,
        },
        quote={
            "quote_number": quote_number,
            "quote_date": quote_date,
            "expiration_date": expiration_date,
            "status": "Draft",
            "project_name": first_summary(summary, "PO_NUMBER")[:255] or None,
            "delivery_address": receiver_address or None,
            "delivery_city": client_city or None,
            "delivery_state": client_state or None,
            "lease_term": None,
            "minimum_lease": None,
            "renewal_policy": None,
            "currency": "USD",
            "subtotal": subtotal,
            "delivery_cost": service_totals["delivery"],
            "pickup_cost": service_totals["pickup"],
            "setup_cost": service_totals["setup"],
            "teardown_cost": service_totals["teardown"],
            "vap_total": vap_total,
            "discount": Decimal("0"),
            "tax": tax,
            "grand_total": grand_total,
            "estimated_delivery_days": None,
            "lead_time": None,
            "insurance_required": False,
            "certificate_required": False,
            "payment_terms": first_summary(summary, "PAYMENT_TERMS")[:255] or None,
            "quote_pdf": str(source_pdf),
            "notes": json.dumps({"source_file": source_pdf.name, "api": "AnalyzeExpense"}),
        },
        line_items=line_items,
        vap_services=vap_services,
    )


def sqlite_connect(path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with foreign key enforcement enabled."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_sqlite_schema(conn: sqlite3.Connection) -> None:
    """Create the local SQLite quote replica schema if it does not exist."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS companies (
            company_id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            website TEXT,
            headquarters_city TEXT,
            headquarters_state TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_name)
        );
        CREATE TABLE IF NOT EXISTS clients (
            client_id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            industry TEXT,
            contact_name TEXT,
            contact_phone TEXT,
            contact_email TEXT,
            billing_address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(client_name, billing_address)
        );
        CREATE TABLE IF NOT EXISTS quotes (
            quote_id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_number TEXT UNIQUE NOT NULL,
            company_id INTEGER NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
            client_id INTEGER NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
            quote_date DATE NOT NULL,
            expiration_date DATE,
            status TEXT DEFAULT 'Draft',
            project_name TEXT,
            delivery_address TEXT,
            delivery_city TEXT,
            delivery_state TEXT,
            lease_term TEXT,
            minimum_lease TEXT,
            renewal_policy TEXT,
            currency TEXT DEFAULT 'USD',
            subtotal NUMERIC DEFAULT 0,
            delivery_cost NUMERIC DEFAULT 0,
            pickup_cost NUMERIC DEFAULT 0,
            setup_cost NUMERIC DEFAULT 0,
            teardown_cost NUMERIC DEFAULT 0,
            vap_total NUMERIC DEFAULT 0,
            discount NUMERIC DEFAULT 0,
            tax NUMERIC DEFAULT 0,
            grand_total NUMERIC DEFAULT 0,
            estimated_delivery_days INTEGER,
            lead_time TEXT,
            insurance_required INTEGER DEFAULT 0,
            certificate_required INTEGER DEFAULT 0,
            payment_terms TEXT,
            quote_pdf TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS quote_line_items (
            line_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id INTEGER NOT NULL REFERENCES quotes(quote_id) ON DELETE CASCADE,
            category TEXT,
            subcategory TEXT,
            product_name TEXT,
            product_type TEXT,
            proposal_type TEXT,
            billing_cycle TEXT,
            size TEXT,
            dimensions TEXT,
            quantity INTEGER NOT NULL DEFAULT 1,
            extended_price NUMERIC DEFAULT 0,
            is_recurring INTEGER DEFAULT 0,
            is_rental INTEGER DEFAULT 1,
            remarks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS vap_services (
            vap_id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id INTEGER NOT NULL REFERENCES quotes(quote_id) ON DELETE CASCADE,
            vap_name TEXT,
            category TEXT,
            proposal_type TEXT,
            billing_cycle TEXT,
            quantity INTEGER DEFAULT 1,
            extended_price NUMERIC DEFAULT 0,
            is_recurring INTEGER DEFAULT 0,
            is_rental INTEGER DEFAULT 0,
            remarks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def db_value(value: Any) -> Any:
    """Convert Python values into database-friendly scalar values."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    return value


def sqlite_upsert(conn: sqlite3.Connection, parsed: ParsedQuote) -> None:
    """Insert or update a parsed quote and its child rows in SQLite."""
    company_id = upsert_sqlite_named(conn, "companies", "company_id", parsed.company, ["company_name"])
    client_id = upsert_sqlite_named(conn, "clients", "client_id", parsed.client, ["client_name", "billing_address"])
    quote = dict(parsed.quote, company_id=company_id, client_id=client_id)
    quote_id = upsert_sqlite_named(conn, "quotes", "quote_id", quote, ["quote_number"])
    conn.execute("DELETE FROM quote_line_items WHERE quote_id = ?", (quote_id,))
    conn.execute("DELETE FROM vap_services WHERE quote_id = ?", (quote_id,))
    insert_many_sqlite(conn, "quote_line_items", [dict(item, quote_id=quote_id) for item in parsed.line_items])
    insert_many_sqlite(conn, "vap_services", [dict(item, quote_id=quote_id) for item in parsed.vap_services])


def upsert_sqlite_named(
    conn: sqlite3.Connection,
    table: str,
    pk: str,
    values: dict[str, Any],
    conflict_cols: list[str],
) -> int:
    """Insert a SQLite row or update it on the supplied conflict columns."""
    columns = list(values)
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{col} = excluded.{col}" for col in columns if col not in conflict_cols)
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT({', '.join(conflict_cols)}) DO UPDATE SET {updates}, updated_at = CURRENT_TIMESTAMP "
        f"RETURNING {pk}"
    )
    params = [db_value(values[col]) for col in columns]
    row = conn.execute(sql, params).fetchone()
    return int(row[0])


def insert_many_sqlite(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    """Insert multiple SQLite rows into a table."""
    if not rows:
        return
    columns = list(rows[0])
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
    conn.executemany(sql, [[db_value(row.get(col)) for col in columns] for row in rows])


def postgres_connect():
    """Open a Postgres connection using credentials from the environment."""
    password = os.getenv("POSTGRES_PASS")
    if not password:
        raise RuntimeError("POSTGRES_PASS is not set. Add it to .env or the process environment.")
    try:
        import psycopg

        return psycopg.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=password,
            dbname=POSTGRES_DB,
        )
    except ImportError:
        try:
            import psycopg2

            return psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                user=POSTGRES_USER,
                password=password,
                dbname=POSTGRES_DB,
            )
        except ImportError as error:
            raise RuntimeError("Install psycopg or psycopg2-binary to write to Postgres.") from error


def postgres_upsert(conn: Any, parsed: ParsedQuote) -> None:
    """Insert or update a parsed quote and its child rows in Postgres."""
    with conn.cursor() as cur:
        company_id = upsert_postgres_named(cur, "companies", "company_id", parsed.company, ["company_name"])
        client_id = upsert_postgres_named(cur, "clients", "client_id", parsed.client, ["client_name", "billing_address"])
        quote = dict(parsed.quote, company_id=company_id, client_id=client_id)
        quote_id = upsert_postgres_named(cur, "quotes", "quote_id", quote, ["quote_number"])
        cur.execute("DELETE FROM quote_line_items WHERE quote_id = %s", (quote_id,))
        cur.execute("DELETE FROM vap_services WHERE quote_id = %s", (quote_id,))
        insert_many_postgres(cur, "quote_line_items", [dict(item, quote_id=quote_id) for item in parsed.line_items])
        insert_many_postgres(cur, "vap_services", [dict(item, quote_id=quote_id) for item in parsed.vap_services])
    conn.commit()


def upsert_postgres_named(cur: Any, table: str, pk: str, values: dict[str, Any], conflict_cols: list[str]) -> int:
    """Insert a Postgres row or update it on the supplied conflict columns."""
    columns = list(values)
    placeholders = ", ".join("%s" for _ in columns)
    updates = ", ".join(f"{col} = EXCLUDED.{col}" for col in columns if col not in conflict_cols)
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT ({', '.join(conflict_cols)}) DO UPDATE SET {updates}, updated_at = CURRENT_TIMESTAMP "
        f"RETURNING {pk}"
    )
    cur.execute(sql, [db_value(values[col]) for col in columns])
    return int(cur.fetchone()[0])


def insert_many_postgres(cur: Any, table: str, rows: list[dict[str, Any]]) -> None:
    """Insert multiple Postgres rows into a table."""
    if not rows:
        return
    columns = list(rows[0])
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('%s' for _ in columns)})"
    for row in rows:
        cur.execute(sql, [db_value(row.get(col)) for col in columns])


def save_raw_response(result: dict[str, Any], source_pdf: Path, output_root: Path) -> Path:
    """Persist the raw Textract response JSON for a processed PDF."""
    target_dir = output_root / source_pdf.stem
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "expense_output.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return target


def quote_pdf_keys(pdf_value: Any) -> set[str]:
    """Return comparable identifiers for a stored or pending quote PDF path."""
    if pdf_value is None:
        return set()
    text = str(pdf_value).strip()
    if not text:
        return set()

    keys = {text}
    path = Path(text)
    keys.add(path.name)
    try:
        keys.add(os.path.normcase(str(path.resolve(strict=False))))
    except OSError:
        keys.add(os.path.normcase(text))
    return keys


def load_processed_quote_pdfs(conn: Any) -> set[str]:
    """Load processed quote PDF identifiers using select quote_pdf from quotes."""
    processed: set[str] = set()
    cur = conn.cursor()
    try:
        cur.execute("select quote_pdf from quotes;")
        for row in cur.fetchall():
            processed.update(quote_pdf_keys(row[0]))
    finally:
        close = getattr(cur, "close", None)
        if close is not None:
            close()
    return processed


def is_pdf_processed(pdf: Path, processed_quote_pdfs: set[str]) -> bool:
    """Return whether a PDF already exists in the processed quote PDF set."""
    return bool(quote_pdf_keys(pdf) & processed_quote_pdfs)


def process_pdfs(args: argparse.Namespace) -> None:
    """Process source PDFs through Textract and persist newly discovered quotes."""
    load_env_file(args.env_file)
    source_dir = Path(args.source_dir)
    pdfs = sorted(source_dir.glob("*.pdf"))[: args.limit]
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found in {source_dir}")

    sqlite_path = Path(args.sqlite_path)
    sqlite_exists = sqlite_path.exists()
    sqlite_conn = sqlite_connect(sqlite_path)
    if not sqlite_exists:
        create_sqlite_schema(sqlite_conn)
    postgres_conn = None if args.sqlite_only else postgres_connect()
    duplicate_check_conn = postgres_conn if postgres_conn is not None else sqlite_conn
    processed_quote_pdfs = load_processed_quote_pdfs(duplicate_check_conn)
    processed = 0
    skipped = 0

    try:
        for pdf in pdfs:
            if is_pdf_processed(pdf, processed_quote_pdfs):
                skipped += 1
                print(f"[{processed + skipped}/{len(pdfs)}] Skipping already processed {pdf.name}")
                continue

            print(f"[{processed + skipped + 1}/{len(pdfs)}] Processing {pdf.name}")
            output_dir = Path(args.output_dir) / pdf.stem
            result = process_document(
                input_path=pdf,
                output_dir=output_dir,
                region=args.region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
                dpi=args.dpi,
            )
            save_raw_response(result, pdf, Path(args.output_dir))
            parsed = parse_quote(result, pdf)
            with sqlite_conn:
                sqlite_upsert(sqlite_conn, parsed)
            if postgres_conn is not None:
                postgres_upsert(postgres_conn, parsed)
                processed_quote_pdfs.update(quote_pdf_keys(parsed.quote.get("quote_pdf")))
            processed += 1
    finally:
        sqlite_conn.close()
        if postgres_conn is not None:
            postgres_conn.close()
    print(f"Done. Ingested {processed} PDF(s), skipped {skipped} duplicate PDF(s).")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the ingestion pipeline."""
    parser = argparse.ArgumentParser(description="Ingest 60 competitor quote PDFs through Textract AnalyzeExpense.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR), help="Folder containing competitor quote PDFs.")
    parser.add_argument("--limit", type=int, default=60, help="Maximum PDFs to process.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Where raw Textract JSON is saved.")
    parser.add_argument("--sqlite-path", default=str(DEFAULT_SQLITE_PATH), help="SQLite replica database path.")
    parser.add_argument("--env-file", default=".env", help="Env file containing AWS credentials and POSTGRES_PASS.")
    parser.add_argument("--region", help="AWS region for Textract.")
    parser.add_argument("--dpi", type=int, default=300, help="PDF render DPI before Textract.")
    parser.add_argument("--sqlite-only", action="store_true", help="Skip Postgres and only write the SQLite replica.")
    return parser


def main() -> None:
    """Run the quote ingestion pipeline from command-line arguments."""
    process_pdfs(build_parser().parse_args())


if __name__ == "__main__":
    main()
