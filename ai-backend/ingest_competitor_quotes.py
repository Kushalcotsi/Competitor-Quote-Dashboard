from typing import Any

import ingest_competitor_quote_expenses as pipeline


def pg_value(value: Any) -> Any:
    """Convert parsed values into Postgres-friendly scalar values."""
    if isinstance(value, bool):
        return value
    return pipeline.db_value(value)


def insert_returning(cur: Any, table: str, pk: str, values: dict[str, Any]) -> int:
    """Insert a row and return its generated primary key."""
    columns = list(values)
    placeholders = ", ".join("%s" for _ in columns)
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) RETURNING {pk}"
    cur.execute(sql, [pg_value(values[col]) for col in columns])
    return int(cur.fetchone()[0])


def get_or_create_company(cur: Any, values: dict[str, Any]) -> int:
    """Find an existing company or create one from parsed quote data."""
    cur.execute(
        "SELECT company_id FROM companies WHERE company_name = %s ORDER BY company_id LIMIT 1",
        (values["company_name"],),
    )
    row = cur.fetchone()
    if row:
        company_id = int(row[0])
        updates = {key: value for key, value in values.items() if key != "company_name" and value is not None}
        if updates:
            assignments = ", ".join(f"{key} = %s" for key in updates)
            cur.execute(
                f"UPDATE companies SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE company_id = %s",
                [pg_value(value) for value in updates.values()] + [company_id],
            )
        return company_id
    return insert_returning(cur, "companies", "company_id", values)


def get_or_create_client(cur: Any, values: dict[str, Any]) -> int:
    """Find an existing client or create one from parsed quote data."""
    cur.execute(
        """
        SELECT client_id
        FROM clients
        WHERE client_name = %s
          AND COALESCE(billing_address, '') = COALESCE(%s, '')
        ORDER BY client_id
        LIMIT 1
        """,
        (values["client_name"], values.get("billing_address")),
    )
    row = cur.fetchone()
    if row:
        client_id = int(row[0])
        updates = {key: value for key, value in values.items() if key != "client_name" and value is not None}
        if updates:
            assignments = ", ".join(f"{key} = %s" for key in updates)
            cur.execute(
                f"UPDATE clients SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE client_id = %s",
                [pg_value(value) for value in updates.values()] + [client_id],
            )
        return client_id
    return insert_returning(cur, "clients", "client_id", values)


def upsert_quote(cur: Any, values: dict[str, Any]) -> int:
    """Insert or update a quote by quote number and return its id."""
    columns = list(values)
    updates = ", ".join(f"{col} = EXCLUDED.{col}" for col in columns if col != "quote_number")
    sql = (
        f"INSERT INTO quotes ({', '.join(columns)}) VALUES ({', '.join('%s' for _ in columns)}) "
        f"ON CONFLICT (quote_number) DO UPDATE SET {updates}, updated_at = CURRENT_TIMESTAMP "
        "RETURNING quote_id"
    )
    cur.execute(sql, [pg_value(values[col]) for col in columns])
    return int(cur.fetchone()[0])


def insert_many(cur: Any, table: str, rows: list[dict[str, Any]]) -> None:
    """Insert multiple child records into a Postgres table."""
    if not rows:
        return
    columns = list(rows[0])
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('%s' for _ in columns)})"
    for row in rows:
        cur.execute(sql, [pg_value(row.get(col)) for col in columns])


def postgres_upsert(conn: Any, parsed: pipeline.ParsedQuote) -> None:
    """Persist a parsed quote and its child rows to Postgres."""
    with conn.cursor() as cur:
        company_id = get_or_create_company(cur, parsed.company)
        client_id = get_or_create_client(cur, parsed.client)
        quote_id = upsert_quote(cur, dict(parsed.quote, company_id=company_id, client_id=client_id))
        cur.execute("DELETE FROM quote_line_items WHERE quote_id = %s", (quote_id,))
        cur.execute("DELETE FROM vap_services WHERE quote_id = %s", (quote_id,))
        insert_many(cur, "quote_line_items", [dict(item, quote_id=quote_id) for item in parsed.line_items])
        insert_many(cur, "vap_services", [dict(item, quote_id=quote_id) for item in parsed.vap_services])
    conn.commit()


def main() -> None:
    """Run the Postgres-backed quote ingestion pipeline."""
    pipeline.postgres_upsert = postgres_upsert
    pipeline.main()


if __name__ == "__main__":
    main()
