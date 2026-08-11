import { query, getCachedDistinct } from '../lib/db';
import React from 'react';
import StateFilters from './StateFilters';
import ExportButtons from './ExportButtons';

export default async function StateCoverage({ searchParams }) {
  const state = searchParams?.state || '';
  const competitor = searchParams?.competitor || '';
  const category = searchParams?.category || '';
  const search = searchParams?.search || '';

  const conditions = [];
  const params = [];
  let paramIndex = 1;

  if (state) {
    conditions.push(`q.delivery_state = $${paramIndex++}`);
    params.push(state);
  }
  if (competitor) {
    conditions.push(`c.company_name = $${paramIndex++}`);
    params.push(competitor);
  }
  if (category) {
    conditions.push(`qli.category = $${paramIndex++}`);
    params.push(category);
  }
  if (search) {
    conditions.push(`(q.quote_number ILIKE $${paramIndex} OR q.delivery_city ILIKE $${paramIndex} OR qli.category ILIKE $${paramIndex} OR qli.subcategory ILIKE $${paramIndex})`);
    params.push(`%${search}%`);
    paramIndex++;
  }

  const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

  const result = await query(`
    SELECT 
      c.company_name as competitor,
      q.quote_number,
      q.delivery_state,
      q.delivery_city,
      qli.category,
      qli.subcategory,
      qli.extended_price as rate
    FROM quotes q
    JOIN companies c ON q.company_id = c.company_id
    JOIN quote_line_items qli ON q.quote_id = qli.quote_id
    ${whereClause}
    ORDER BY q.delivery_state ASC
  `, params);

  const rows = result.rows;

  // Aggregate states
  const stateCounts = {};
  rows.forEach(r => {
    const s = r.delivery_state || 'Unknown';
    stateCounts[s] = (stateCounts[s] || 0) + 1;
  });
  
  const sortedStates = Object.keys(stateCounts).map(s => ({state: s, count: stateCounts[s]})).sort((a,b) => b.count - a.count);
  const maxCount = sortedStates.length ? sortedStates[0].count : 1;

  // Fetch unique filter options independently from in-memory cache
  const [uniqueStates, uniqueCompetitors, uniqueCategories] = await Promise.all([
    getCachedDistinct('delivery_state', 'quotes'),
    getCachedDistinct('company_name', 'companies'),
    getCachedDistinct('category', 'quote_line_items')
  ]);

  return (
    <section id="states" className="tabpanel">
      <div className="kpis">
        <div className="kpi"><small>States represented</small><b>{sortedStates.length}</b></div>
        <div className="kpi"><small>Quote records listed</small><b>{rows.length}</b></div>
        <div className="kpi"><small>Competitors represented</small><b>{new Set(rows.map(r=>r.competitor)).size}</b></div>
        <div className="kpi"><small>Provided state-count total</small><b>{rows.length}</b></div>
      </div>

      <div className="panel filters">
        <StateFilters 
          uniqueStates={uniqueStates} 
          uniqueCompetitors={uniqueCompetitors} 
          uniqueCategories={uniqueCategories} 
        />
      </div>

      <div className="state-layout">
        <div className="panel">
          <div className="toolbar">States represented</div>
          <div className="bars">
            {sortedStates.map(x => (
              <div className="barrow" key={x.state}>
                <div className="barlabel">{x.state}</div>
                <div className="track"><div className="fill" style={{width: `${(x.count/maxCount)*100}%`}}></div></div>
                <b>{x.count}</b>
              </div>
            ))}
          </div>
        </div>
        
        <div className="panel">
          <div className="toolbar">
            <span>{rows.length} quote records</span>
            <ExportButtons tableId="stateTable" filename="State_Coverage" />
          </div>
          <div className="tablewrap">
            <table id="stateTable" className="state-table">
              <thead>
                <tr>
                  <th>Competitor</th>
                  <th>Quote</th>
                  <th>Delivery State</th>
                  <th>City</th>
                  <th>Product Category</th>
                  <th>Subcategory</th>
                  <th>Rate</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td><b>{r.competitor}</b></td>
                    <td>{r.quote_number}</td>
                    <td><span className="badge green">{r.delivery_state}</span></td>
                    <td>{r.delivery_city || '—'}</td>
                    <td>{r.category}</td>
                    <td>{r.subcategory}</td>
                    <td>{r.rate ? `$${Number(r.rate).toFixed(2)}` : '—'}</td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan="7" style={{padding:50, textAlign:'center'}}>No quote records match the selected filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}
