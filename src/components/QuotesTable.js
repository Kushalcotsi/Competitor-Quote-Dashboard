import { query, getCachedDistinct } from '../lib/db';
import React from 'react';
import QuotesFilters from './QuotesFilters';
import ExportButtons from './ExportButtons';

export default async function QuotesTable({ searchParams }) {
  // Parse query parameters for server-side filtering
  const state = searchParams?.state || '';
  const category = searchParams?.category || '';
  const subcategory = searchParams?.subcategory || '';
  const search = searchParams?.search || '';

  const conditions = [];
  const params = [];
  let paramIndex = 1;

  if (state) {
    conditions.push(`q.delivery_state = $${paramIndex++}`);
    params.push(state);
  }
  if (category) {
    conditions.push(`qli.category = $${paramIndex++}`);
    params.push(category);
  }
  if (subcategory) {
    conditions.push(`qli.subcategory = $${paramIndex++}`);
    params.push(subcategory);
  }
  if (search) {
    conditions.push(`(q.notes ILIKE $${paramIndex} OR qli.category ILIKE $${paramIndex} OR qli.subcategory ILIKE $${paramIndex} OR q.delivery_state ILIKE $${paramIndex})`);
    params.push(`%${search}%`);
    paramIndex++;
  }

  const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

  const result = await query(`
    SELECT 
      qli.category,
      qli.subcategory,
      q.delivery_state,
      qli.extended_price as unit_price,
      qli.billing_cycle,
      q.lease_term,
      q.delivery_cost,
      q.pickup_cost,
      q.estimated_delivery_days,
      q.notes
    FROM quote_line_items qli
    JOIN quotes q ON qli.quote_id = q.quote_id
    ${whereClause}
    ORDER BY qli.category ASC, qli.subcategory ASC
  `, params);

  const rows = result.rows;

  // Group by category
  const categories = {};
  rows.forEach(r => {
    const cat = r.category || 'Uncategorized';
    if (!categories[cat]) categories[cat] = [];
    categories[cat].push(r);
  });

  // Fetch unique filter options independently from in-memory cache
  const [uniqueStates, uniqueCategories, uniqueSubcategories] = await Promise.all([
    getCachedDistinct('delivery_state', 'quotes'),
    getCachedDistinct('category', 'quote_line_items'),
    getCachedDistinct('subcategory', 'quote_line_items')
  ]);

  return (
    <section id="comparison" className="tabpanel">
      <div className="kpis">
        <div className="kpi"><small>Visible categories</small><b>{Object.keys(categories).length}</b></div>
        <div className="kpi"><small>Total line items</small><b>{rows.length}</b></div>
        <div className="kpi"><small>Unique subcategories</small><b>{new Set(rows.map(r => r.subcategory)).size}</b></div>
        <div className="kpi"><small>Rows missing rates</small><b>{rows.filter(r => !r.unit_price).length}</b></div>
      </div>

      <div className="panel filters">
        <QuotesFilters 
          uniqueStates={uniqueStates} 
          uniqueCategories={uniqueCategories} 
          uniqueSubcategories={uniqueSubcategories} 
        />
      </div>

      <div className="panel">
        <div className="toolbar">
          <div>
            <span>{rows.length} rows</span>
            <span className="muted" style={{ marginLeft: 12 }}>Product hierarchy is visually nested by category.</span>
          </div>
          {/* <ExportButtons tableId="quoteTable" filename="Quotes_Comparison" /> */}
        </div>
        <div className="tablewrap">
          <table id="quoteTable">
            <thead>
              <tr>
                <th className="sticky1">Category</th>
                <th className="sticky2">Product Size / Subcategory</th>
                <th>State Coverage</th>
                <th>Rate</th>
                <th>Rate Basis / Billing Cycle</th>
                <th>Lease Term</th>
                <th>D&I / Pickup</th>
                <th>Delivery Timeframe</th>
                <th>Pricing / Data Notes</th>
              </tr>
            </thead>
            <tbody>
              {Object.keys(categories).map(cat => {
                const catRows = categories[cat];
                return (
                  <React.Fragment key={cat}>
                    <tr className="group">
                      <td colSpan="9">
                        {cat}
                        <span>{catRows.length} explicit quotes in this category</span>
                      </td>
                    </tr>
                    {catRows.map((r, i) => (
                      <tr key={i}>
                        <td className="sticky1">{cat}</td>
                        <td className="sticky2">
                          <span style={{paddingLeft: 22}}>└─ {r.subcategory || 'General'}</span>
                        </td>
                        <td><span className="badge blue">{r.delivery_state || 'Unknown'}</span></td>
                        <td>{r.unit_price ? `$${Number(r.unit_price).toFixed(2)}` : 'N/A'}</td>
                        <td>{r.billing_cycle || 'N/A'}</td>
                        <td>{r.lease_term || 'Unknown'}</td>
                        <td>
                          {r.delivery_cost ? `$${r.delivery_cost} D / ` : 'N/A D / '}
                          {r.pickup_cost ? `$${r.pickup_cost} R` : 'N/A R'}
                        </td>
                        <td>{r.estimated_delivery_days ? `${r.estimated_delivery_days} days` : 'N/A'}</td>
                        <td className="muted">{r.notes || '—'}</td>
                      </tr>
                    ))}
                  </React.Fragment>
                );
              })}
              {rows.length === 0 && (
                <tr><td colSpan="9" style={{padding:50, textAlign:'center'}}>No quote records match the selected filters.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
