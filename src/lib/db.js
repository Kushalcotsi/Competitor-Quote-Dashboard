import { Pool } from 'pg';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: {
    rejectUnauthorized: false
  }
});

export async function query(text, params) {
  const start = Date.now();
  const res = await pool.query(text, params);
  const duration = Date.now() - start;
  console.log('executed query', { text: text.trim().substring(0, 50) + '...', duration, rows: res.rowCount });
  return res;
}

// In-memory cache for distinct filter options to drastically speed up page loads
const distinctCache = {};

export async function getCachedDistinct(column, table) {
  const key = `${table}_${column}`;
  if (distinctCache[key]) {
    return distinctCache[key];
  }
  
  const start = Date.now();
  const res = await pool.query(`SELECT DISTINCT ${column} FROM ${table} WHERE ${column} IS NOT NULL ORDER BY ${column}`);
  const duration = Date.now() - start;
  console.log('executed distinct query (CACHING)', { table, column, duration, rows: res.rowCount });
  
  const values = res.rows.map(r => r[column]);
  distinctCache[key] = values;
  
  return values;
}
