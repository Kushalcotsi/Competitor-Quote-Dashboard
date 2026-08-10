import { query } from '../lib/db';

export default async function StateCoverage() {
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
    ORDER BY q.delivery_state ASC
  `);

  const rows = result.rows;

  // Aggregate states
  const stateCounts = {};
  rows.forEach(r => {
    const s = r.delivery_state || 'Unknown';
    stateCounts[s] = (stateCounts[s] || 0) + 1;
  });
  
  const sortedStates = Object.keys(stateCounts).map(s => ({state: s, count: stateCounts[s]})).sort((a,b) => b.count - a.count);
  const maxCount = sortedStates.length ? sortedStates[0].count : 1;

  const uniqueStates = [...new Set(rows.map(r => r.delivery_state).filter(Boolean))].sort();
  const uniqueCompetitors = [...new Set(rows.map(r => r.competitor).filter(Boolean))].sort();
  const uniqueCategories = [...new Set(rows.map(r => r.category).filter(Boolean))].sort();

  return (
    <section id="states" className="tabpanel">
      <div className="kpis">
        <div className="kpi"><small>States represented</small><b>{sortedStates.length}</b></div>
        <div className="kpi"><small>Quote records listed</small><b>{rows.length}</b></div>
        <div className="kpi"><small>Competitors represented</small><b>{new Set(rows.map(r=>r.competitor)).size}</b></div>
        <div className="kpi"><small>Provided state-count total</small><b>{rows.length}</b></div>
      </div>

      <div className="panel filters">
        <div className="stategrid">
          <div>
            <label>Delivery State</label>
            <select>
              <option>All states</option>
              {uniqueStates.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label>Competitor</label>
            <select>
              <option>All competitors</option>
              {uniqueCompetitors.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label>Category</label>
            <select>
              <option>All categories</option>
              {uniqueCategories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div><label>Search</label><input placeholder="Search..." /></div>
          <button className="btn secondary">Reset</button>
          <button className="btn primary">Export CSV</button>
        </div>
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
          </div>
          <div className="tablewrap">
            <table className="state-table">
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
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}
