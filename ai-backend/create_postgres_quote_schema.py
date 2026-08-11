import argparse
import os
from pathlib import Path

from textract_expenseAPI.aws_textract_expense import load_env_file


POSTGRES_HOST = "ai-test-quotes-database-1.ci34282eytrl.us-east-1.rds.amazonaws.com"
POSTGRES_PORT = 5432
POSTGRES_USER = "postgres"
DEFAULT_POSTGRES_DB = "competitor_analysis"


SCHEMA_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'quote_status') THEN
        CREATE TYPE quote_status AS ENUM ('Draft', 'Accepted', 'Rejected', 'Expired');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'proposal_type_enum') THEN
        CREATE TYPE proposal_type_enum AS ENUM ('Quote', 'Bid', 'Lease Proposal', 'Rental Quote');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'billing_cycle_enum') THEN
        CREATE TYPE billing_cycle_enum AS ENUM ('Daily', 'Weekly', 'Monthly', '28-Day', '4 Week');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS companies (
    company_id BIGSERIAL PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    website VARCHAR(500),
    headquarters_city VARCHAR(100),
    headquarters_state VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clients (
    client_id BIGSERIAL PRIMARY KEY,
    client_name VARCHAR(255) NOT NULL,
    industry VARCHAR(100),
    contact_name VARCHAR(255),
    contact_phone VARCHAR(30),
    contact_email VARCHAR(255),
    billing_address TEXT,
    city VARCHAR(100),
    state VARCHAR(100),
    zip_code VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quotes (
    quote_id BIGSERIAL PRIMARY KEY,
    quote_number VARCHAR(100) UNIQUE NOT NULL,
    company_id BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
    client_id BIGINT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    quote_date DATE NOT NULL,
    expiration_date DATE,
    status quote_status DEFAULT 'Draft',
    project_name VARCHAR(255),
    delivery_address TEXT,
    delivery_city VARCHAR(100),
    delivery_state VARCHAR(100),
    lease_term VARCHAR(100),
    minimum_lease VARCHAR(100),
    renewal_policy TEXT,
    currency CHAR(3) DEFAULT 'USD',
    subtotal NUMERIC(12,2) DEFAULT 0,
    delivery_cost NUMERIC(12,2) DEFAULT 0,
    pickup_cost NUMERIC(12,2) DEFAULT 0,
    setup_cost NUMERIC(12,2) DEFAULT 0,
    teardown_cost NUMERIC(12,2) DEFAULT 0,
    vap_total NUMERIC(12,2) DEFAULT 0,
    discount NUMERIC(12,2) DEFAULT 0,
    tax NUMERIC(12,2) DEFAULT 0,
    grand_total NUMERIC(12,2) DEFAULT 0,
    estimated_delivery_days INTEGER,
    lead_time VARCHAR(100),
    insurance_required BOOLEAN DEFAULT FALSE,
    certificate_required BOOLEAN DEFAULT FALSE,
    payment_terms VARCHAR(255),
    quote_pdf TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quote_line_items (
    line_item_id BIGSERIAL PRIMARY KEY,
    quote_id BIGINT NOT NULL REFERENCES quotes(quote_id) ON DELETE CASCADE,
    category VARCHAR(150),
    subcategory VARCHAR(150),
    product_name VARCHAR(255),
    product_type VARCHAR(150),
    proposal_type proposal_type_enum,
    billing_cycle billing_cycle_enum,
    size VARCHAR(100),
    dimensions VARCHAR(255),
    quantity INTEGER NOT NULL DEFAULT 1,
    extended_price NUMERIC(12,2) DEFAULT 0,
    is_recurring BOOLEAN DEFAULT FALSE,
    is_rental BOOLEAN DEFAULT TRUE,
    remarks TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vap_services (
    vap_id BIGSERIAL PRIMARY KEY,
    quote_id BIGINT NOT NULL REFERENCES quotes(quote_id) ON DELETE CASCADE,
    vap_name VARCHAR(255),
    category VARCHAR(150),
    proposal_type proposal_type_enum,
    billing_cycle billing_cycle_enum,
    quantity INTEGER DEFAULT 1,
    extended_price NUMERIC(12,2) DEFAULT 0,
    is_recurring BOOLEAN DEFAULT FALSE,
    is_rental BOOLEAN DEFAULT FALSE,
    remarks TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(database: str):
    """Open a Postgres connection for schema creation."""
    password = os.getenv("POSTGRES_PASS")
    if not password:
        raise RuntimeError("POSTGRES_PASS is not set. Check .env.")
    try:
        import psycopg

        return psycopg.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=password,
            dbname=database,
        )
    except ImportError:
        import psycopg2

        return psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=password,
            dbname=database,
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for schema creation."""
    parser = argparse.ArgumentParser(description="Create the quote ingestion schema in Postgres.")
    parser.add_argument(
        "--database",
        default=DEFAULT_POSTGRES_DB,
        help="Postgres database where the quote schema should be created.",
    )
    parser.add_argument("--env-file", default=".env", help="Env file containing POSTGRES_PASS.")
    return parser


def main() -> None:
    """Create the Postgres quote schema from command-line arguments."""
    args = build_parser().parse_args()
    load_env_file(Path(args.env_file))
    conn = connect(args.database)
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
    print(f"Postgres quote schema is ready in database: {args.database}")


if __name__ == "__main__":
    main()
