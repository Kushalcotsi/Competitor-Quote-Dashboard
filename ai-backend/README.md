## Supported Inputs

- PDF, including multi-page PDFs
- PNG
- JPG / JPEG

## Installation

Use Python 3.11 or newer.

```bash
cd invoice_ocr
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On Linux/macOS, activate the virtual environment with:

```bash
source .venv/bin/activate
```
## How To Run

Place invoice files in `input/`, or pass any supported file path.

## AWS Textract OCR, Tables, And Forms

Use AWS Textract when you want managed OCR, table extraction, and form/key-value extraction with the `TABLES` and `FORMS` features:

```bash
pip install -r aws_textract_requirements.txt
```

Then fill in your AWS values.

### Textract Pipeline

These scripts are related in sequence:

1. `aws_textract_ocr.py` sends the document to AWS Textract and saves the raw response.
2. `process_textract_json.py` converts the raw Textract response into clean `line` and `table` blocks, with table HTML.
3. `annotate_processed_json.py` draws bounding boxes from the processed JSON on the source PDF.

Run AWS Textract OCR and save the raw JSON response:

```bash
python aws_textract_ocr.py input/inv2.PDF -o output/textract_inv2
```

This creates:

```text
output/textract_inv2/output.json
```

Process the raw Textract JSON into final line/table blocks:

```bash
python process_textract_json.py output/textract_inv2/output.json -o output/textract_inv2/processed_output_html.json
```

This creates:

```text
output/textract_inv2/processed_output_html.json
```

Draw bounding boxes from the processed JSON on the source PDF:

```bash
python annotate_processed_json.py output/textract_inv2/processed_output_html.json --pdf input/inv2.PDF -o output/textract_inv2/processed_annotated
```

This creates annotated PNG pages and a combined annotated PDF in:

```text
output/textract_inv2/processed_annotated/
```

### Analyze Expense API

Use `aws_textract_expense.py` when you want Textract's invoice/receipt-focused `AnalyzeExpense` response with `SummaryFields` and `LineItemGroups`:

```bash
python aws_textract_expense.py input/inv2.PDF -o output/textract_inv2_expense
```

This creates:

```text
output/textract_inv2_expense/expense_output.json
```

Process the raw AnalyzeExpense JSON into clean summary fields and line items with bounding boxes:

```bash
python process_expense_json.py output/textract_inv2_expense/expense_output.json -o output/textract_inv2_expense/processed_expense_output.json
```

This creates:

```text
output/textract_inv2_expense/processed_expense_output.json
```

Draw bounding boxes for expense summary fields and line items on the source PDF:

```bash
python process_expense_json.py output/textract_inv2_expense/expense_output.json -o output/textract_inv2_expense/processed_expense_output.json --pdf input/inv2.PDF --annotate-dir output/textract_inv2_expense/expense_annotated
```

This creates annotated PNG pages and a combined annotated PDF in:

```text
output/textract_inv2_expense/expense_annotated/
```


## Competitor Quote Ingestion

The quote ingestion scripts process competitor quote PDFs with AWS Textract AnalyzeExpense, map extracted data into the quote database schema, and write the same records to a local SQLite replica.

### Scripts

- `ingest_competitor_quote_expenses.py`: core ingestion pipeline.
- `ingest_competitor_quotes.py`: Postgres writer wrapper.
- `ingest_competitor_analysis_quotes_safe.py`: recommended runner for `competitor_analysis`; sanitizes output folder names for Windows.
- `create_postgres_quote_schema.py`: creates quote tables in the selected Postgres database.
- `generate_key_findings.py`: queries quote tables and generates Key Findings copy with Claude on AWS Bedrock.
- `quotes_replica.sqlite3`: local SQLite replica created by ingestion.

Target tables: `companies`, `clients`, `quotes`, `quote_line_items`, `vap_services`.

### Requirements

Install dependencies:

```powershell
pip install -r requirements.txt
```

`.env` must contain valid AWS credentials and the Postgres password:

```env
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...
AWS_REGION=us-east-1
POSTGRES_PASS=...
```

If AWS credentials are temporary, refresh them before running. Expired credentials cause `UnrecognizedClientException: The security token included in the request is invalid`.

### Database Setup

Create the database once if it does not already exist:

```sql
CREATE DATABASE competitor_analysis;
```

Then create the quote schema inside that database:

```powershell
python create_postgres_quote_schema.py --database competitor_analysis --env-file .env
```

### Run Ingestion

Recommended command:

```powershell
python ingest_competitor_analysis_quotes_safe.py
```

By default this reads PDFs from `D:\willscot-competitor-analysis\Competitor Quotes` and processes up to 60 PDFs.

Useful commands:

```powershell
python ingest_competitor_analysis_quotes_safe.py --limit 1
python ingest_competitor_analysis_quotes_safe.py --limit 50
python ingest_competitor_analysis_quotes_safe.py --limit 1 --sqlite-only
python ingest_competitor_analysis_quotes_safe.py --source-dir "D:\path\to\pdfs"
python ingest_competitor_analysis_quotes_safe.py --sqlite-path .\my_quotes.sqlite3
```

To process all PDFs from the latest import folder:

```powershell
python ingest_competitor_analysis_quotes_safe.py `
  --source-dir "D:\willscot-competitor-analysis\Competitor Quotes\New folder" `
  --env-file .env `
  --limit 83
```

Raw Textract JSON is saved under `output\competitor_quotes_expense\safe-pdf-name\expense_output.json`.

The local SQLite replica is saved by default as `quotes_replica.sqlite3`.

### Duplicate PDF Handling

Before a PDF is sent to Textract, the ingestion pipeline loads already processed files with:

```sql
select quote_pdf from quotes;
```

The script compares those stored paths with the pending source PDF and skips matching files. This prevents spending Textract time on PDFs that have already been processed.

Quote rows are still upserted by `quote_number`. If two different PDFs produce the same `quote_number`, the later file in sorted filename order updates the existing quote row. The child rows in `quote_line_items` and `vap_services` are deleted and reinserted for that quote.

### Truncate And Reprocess

Use this only when you intentionally want to delete existing quote data from AWS RDS and rebuild from PDFs:

```sql
TRUNCATE TABLE quote_line_items, vap_services, quotes, clients, companies RESTART IDENTITY CASCADE;
```

After truncation, run ingestion with a source folder and a limit high enough to include every PDF.

For the `New folder` import, 83 PDFs were processed. Because three pairs shared the same extracted `quote_number`, the final `quotes` table contained 80 rows.

### Key Findings Generation

`generate_key_findings.py` builds the Key Findings dashboard copy from database evidence. It runs SQL summaries over the quote tables, passes the evidence to Claude through AWS Bedrock, and prints the model response.

Run:

```powershell
python generate_key_findings.py --bedrock-region us-east-1
```

Print the SQL evidence before the LLM response:

```powershell
python generate_key_findings.py --print-evidence
```

The default Bedrock model is Claude Haiku 4.5:

```text
us.anthropic.claude-haiku-4-5-20251001-v1:0
```

Claude 3.5 Haiku is no longer used because AWS Bedrock reports that model version as end-of-life.

### Notes

- Reruns skip already processed PDFs by checking `quotes.quote_pdf`.
- Reruns are safe for existing quote numbers because `quotes.quote_number` is upserted.
- The script deletes and reinserts line items and VAP/service rows for an existing quote during rerun.
- The safe runner avoids Windows folder errors caused by PDF names that end with a space, such as `LONESTAR Mobile Storage Quote - 20FT .pdf`.
- Use `ingest_competitor_analysis_quotes_safe.py` for normal ingestion work.
