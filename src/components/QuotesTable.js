import { query } from '../lib/db';

export default async function QuotesTable() {
  const result = await query(`
    SELECT 
      qli.category,
      qli.subcategory,
      q.delivery_state,
      qli.unit_price,
      qli.billing_cycle,
      q.lease_term,
      q.delivery_cost,
      q.pickup_cost,
      q.estimated_delivery_days,
      q.notes
    FROM core.quote_line_items qli
    JOIN core.quotes q ON qli.quote_id = q.quote_id
    ORDER BY qli.category ASC, qli.subcategory ASC
  `);

  const rows = result.rows;

  // Group by category
  const categories = {};
  rows.forEach(r => {
    const cat = r.category || 'Uncategorized';
    if (!categories[cat]) categories[cat] = [];
    categories[cat].push(r);
  });

  const uniqueStates = [...new Set(rows.map(r => r.delivery_state).filter(Boolean))].sort();
  const uniqueCategories = [...new Set(rows.map(r => r.category).filter(Boolean))].sort();
  const uniqueSubcategories = [...new Set(rows.map(r => r.subcategory).filter(Boolean))].sort();

  return (
    <section id="comparison" className="tabpanel">
      <div className="kpis">
        <div className="kpi"><small>Visible categories</small><b>{Object.keys(categories).length}</b></div>
        <div className="kpi"><small>Total line items</small><b>{rows.length}</b></div>
        <div className="kpi"><small>Unique subcategories</small><b>{new Set(rows.map(r => r.subcategory)).size}</b></div>
        <div className="kpi"><small>Rows missing rates</small><b>{rows.filter(r => !r.unit_price).length}</b></div>
      </div>

      <div className="panel filters">
        <div className="grid">
          <div>
            <label>State</label>
            <select>
              <option>All states</option>
              {uniqueStates.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label>Category</label>
            <select>
              <option>All categories</option>
              {uniqueCategories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label>Subcategory</label>
            <select>
              <option>All subcategories</option>
              {uniqueSubcategories.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div><label>Search</label><input placeholder="Search..." /></div>
          <button className="btn secondary">Reset</button>
        </div>
        <div className="note"><b>Database Connected:</b> Data is being pulled live from the <code>core</code> schema.</div>
      </div>

      <div className="panel">
        <div className="toolbar">
          <span>{rows.length} rows</span>
          <span className="muted">Product hierarchy is visually nested by category.</span>
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
                <tr><td colSpan="9" style={{padding:50, textAlign:'center'}}>No records found in core schema.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

// Need to import React for React.Fragment
import React from 'react';
