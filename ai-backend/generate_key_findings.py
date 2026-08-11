import argparse
import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import boto3

from textract_expenseAPI.aws_textract_expense import load_env_file


POSTGRES_HOST = "ai-test-quotes-database-1.ci34282eytrl.us-east-1.rds.amazonaws.com"
POSTGRES_PORT = 5432
POSTGRES_USER = "postgres"
DEFAULT_POSTGRES_DB = "competitor_analysis"
DEFAULT_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_BEDROCK_REGION = "us-east-1"


SYSTEM_PROMPT = """
You are a pricing analyst creating the Key Findings section for a competitor
quote analysis dashboard.

Use only the database evidence supplied by the user. Do not invent quote terms,
companies, line item types, or pricing behavior that is not supported by the
data. If evidence is thin, say so plainly.

Return a JSON object with exactly these keys:
- quote_structure: array of 5 bullet strings, decscribing recurring vs one-time charges, delivery/pickup/setup/teardown separation, and VAP/service fees
- types_of_line_items: array of 5 bullet strings, describing line item categories, lease terms, insurance, delivery and setup charges, and any other notable line item types  
- pricing_structure_insights: array of 5 bullet strings, describing split between recurring and one-time charges, what charges account for the majority of quote totals, and any notable pricing patterns

Write bullets in business-friendly language similar to a dashboard card. Focus
on recurring vs one-time charges, delivery/pickup/setup/teardown separation,
VAP/service fees, billing cycles, lease terms, totals, and quote coverage.
"""


KEY_FINDINGS_QUERIES: dict[str, str] = {
    "summary_counts": """
        SELECT
            COUNT(*) AS quote_count,
            COUNT(DISTINCT company_id) AS company_count,
            COUNT(DISTINCT client_id) AS client_count,
            COUNT(*) FILTER (WHERE delivery_cost > 0) AS quotes_with_delivery_cost,
            COUNT(*) FILTER (WHERE pickup_cost > 0) AS quotes_with_pickup_cost,
            COUNT(*) FILTER (WHERE setup_cost > 0) AS quotes_with_setup_cost,
            COUNT(*) FILTER (WHERE teardown_cost > 0) AS quotes_with_teardown_cost,
            COUNT(*) FILTER (WHERE vap_total > 0) AS quotes_with_vap_total,
            COUNT(*) FILTER (WHERE lease_term IS NOT NULL AND lease_term <> '') AS quotes_with_lease_term,
            COUNT(*) FILTER (WHERE payment_terms IS NOT NULL AND payment_terms <> '') AS quotes_with_payment_terms,
            ROUND(AVG(grand_total), 2) AS avg_grand_total,
            ROUND(MIN(grand_total), 2) AS min_grand_total,
            ROUND(MAX(grand_total), 2) AS max_grand_total
        FROM quotes;
    """,
    "company_quote_counts": """
        SELECT
            c.company_name,
            COUNT(*) AS quote_count,
            ROUND(AVG(q.grand_total), 2) AS avg_grand_total,
            ROUND(SUM(q.grand_total), 2) AS total_grand_total
        FROM quotes q
        JOIN companies c ON c.company_id = q.company_id
        GROUP BY c.company_name
        ORDER BY quote_count DESC, c.company_name
        LIMIT 15;
    """,
    "line_item_categories": """
        SELECT
            COALESCE(category, 'Uncategorized') AS category,
            COUNT(*) AS line_item_count,
            SUM(quantity) AS total_quantity,
            ROUND(SUM(extended_price), 2) AS total_extended_price,
            ROUND(AVG(extended_price), 2) AS avg_extended_price,
            COUNT(*) FILTER (WHERE is_recurring) AS recurring_count,
            COUNT(*) FILTER (WHERE is_rental) AS rental_count
        FROM quote_line_items
        GROUP BY COALESCE(category, 'Uncategorized')
        ORDER BY line_item_count DESC, total_extended_price DESC NULLS LAST;
    """,
    "vap_categories": """
        SELECT
            COALESCE(category, 'Uncategorized') AS category,
            COUNT(*) AS service_count,
            SUM(quantity) AS total_quantity,
            ROUND(SUM(extended_price), 2) AS total_extended_price,
            ROUND(AVG(extended_price), 2) AS avg_extended_price,
            COUNT(*) FILTER (WHERE is_recurring) AS recurring_count,
            COUNT(*) FILTER (WHERE is_rental) AS rental_count
        FROM vap_services
        GROUP BY COALESCE(category, 'Uncategorized')
        ORDER BY service_count DESC, total_extended_price DESC NULLS LAST;
    """,
    "billing_cycles": """
        SELECT
            billing_cycle,
            COUNT(*) AS item_count,
            ROUND(SUM(extended_price), 2) AS total_extended_price
        FROM (
            SELECT billing_cycle, extended_price FROM quote_line_items
            UNION ALL
            SELECT billing_cycle, extended_price FROM vap_services
        ) items
        WHERE billing_cycle IS NOT NULL
        GROUP BY billing_cycle
        ORDER BY item_count DESC;
    """,
    "service_cost_presence": """
        SELECT
            COUNT(*) FILTER (WHERE delivery_cost > 0) AS delivery_quotes,
            ROUND(AVG(NULLIF(delivery_cost, 0)), 2) AS avg_delivery_cost,
            COUNT(*) FILTER (WHERE pickup_cost > 0) AS pickup_quotes,
            ROUND(AVG(NULLIF(pickup_cost, 0)), 2) AS avg_pickup_cost,
            COUNT(*) FILTER (WHERE setup_cost > 0) AS setup_quotes,
            ROUND(AVG(NULLIF(setup_cost, 0)), 2) AS avg_setup_cost,
            COUNT(*) FILTER (WHERE teardown_cost > 0) AS teardown_quotes,
            ROUND(AVG(NULLIF(teardown_cost, 0)), 2) AS avg_teardown_cost,
            COUNT(*) FILTER (WHERE vap_total > 0) AS vap_quotes,
            ROUND(AVG(NULLIF(vap_total, 0)), 2) AS avg_vap_total
        FROM quotes;
    """,
    "sample_terms": """
        SELECT
            quote_number,
            lease_term,
            minimum_lease,
            renewal_policy,
            payment_terms,
            quote_pdf
        FROM quotes
        WHERE COALESCE(lease_term, minimum_lease, renewal_policy, payment_terms) IS NOT NULL
        ORDER BY quote_date DESC, quote_id DESC
        LIMIT 20;
    """,
}


def connect(database: str):
    """Open a Postgres connection to the quote analysis database."""
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


def json_value(value: Any) -> Any:
    """Convert database values into JSON-serializable values."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def fetch_named_query(cur: Any, sql: str) -> list[dict[str, Any]]:
    """Execute a SQL query and return rows as dictionaries."""
    cur.execute(sql)
    columns = [desc[0] for desc in cur.description]
    return [
        {column: json_value(value) for column, value in zip(columns, row)}
        for row in cur.fetchall()
    ]


def fetch_key_findings_data(conn: Any) -> dict[str, list[dict[str, Any]]]:
    """Run all database queries needed for the key findings prompt."""
    with conn.cursor() as cur:
        return {
            name: fetch_named_query(cur, sql)
            for name, sql in KEY_FINDINGS_QUERIES.items()
        }


def build_user_prompt(data: dict[str, list[dict[str, Any]]]) -> str:
    """Build the user prompt containing SQL-derived evidence for the LLM."""
    return (
        "Create Key Findings dashboard copy from this SQL-derived evidence. "
        "Keep each bullet short and specific. Evidence JSON:\n"
        f"{json.dumps(data, indent=2)}"
    )


def call_bedrock_claude(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int,
    region: str,
) -> str:
    """Call Claude through Amazon Bedrock and return the text response."""
    client = boto3.client("bedrock-runtime", region_name=region)
    response = client.invoke_model(
        modelId=model,
        body=json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "system": system_prompt.strip(),
                "messages": [{"role": "user", "content": user_prompt}],
            }
        ),
    )
    payload = json.loads(response["body"].read())
    return "\n".join(
        block.get("text", "")
        for block in payload.get("content", [])
        if block.get("type") == "text"
    ).strip()


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for key findings generation."""
    parser = argparse.ArgumentParser(description="Generate quote-analysis key findings with Claude on Bedrock.")
    parser.add_argument("--database", default=DEFAULT_POSTGRES_DB, help="Postgres database to query.")
    parser.add_argument("--env-file", default=".env", help="Env file with POSTGRES_PASS and AWS credentials.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Bedrock Claude model ID or inference profile ID.")
    parser.add_argument("--bedrock-region", default=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or DEFAULT_BEDROCK_REGION, help="AWS region for the Bedrock Runtime client.")
    parser.add_argument("--max-tokens", type=int, default=900, help="Maximum Claude response tokens.")
    parser.add_argument("--print-evidence", action="store_true", help="Print SQL evidence before the LLM response.")
    return parser


def main() -> None:
    """Query quote tables, ask Claude for key findings, and print the response."""
    args = build_parser().parse_args()
    load_env_file(Path(args.env_file))
    conn = connect(args.database)
    
    try:
        data = fetch_key_findings_data(conn)

        if args.print_evidence:
            print(json.dumps(data, indent=2))

        response = call_bedrock_claude(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(data),
            model=args.model,
            max_tokens=args.max_tokens,
            region=args.bedrock_region,
        )
        print("Generated Key Findings:")
        print(response)
        
        # Clean the response in case Claude wrapped it in ```json
        clean_response = response.strip()
        if clean_response.startswith("```json"):
            clean_response = clean_response[7:]
        elif clean_response.startswith("```"):
            clean_response = clean_response[3:]
        if clean_response.endswith("```"):
            clean_response = clean_response[:-3]
        clean_response = clean_response.strip()
        
        # Save to database cache for Next.js UI
        print("Saving findings to database cache...")
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO key_findings_cache (insights_json) VALUES (%s)",
                (clean_response,)
            )
        conn.commit()
        print("Done!")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
