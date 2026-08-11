import { query } from '../lib/db';
import React from 'react';
import UpdateInsightsButton from './UpdateInsightsButton';

export default async function KeyFindings() {
  const result = await query(`
    SELECT insights_json, created_at 
    FROM key_findings_cache 
    ORDER BY created_at DESC 
    LIMIT 1
  `);

  if (result.rows.length === 0) {
    return (
      <section id="findings" className="tabpanel">
        <div className="panel" style={{ minHeight: '500px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="empty-state">
            <h3>AI Insights Pending</h3>
            <p>Waiting for the backend AI pipeline to generate the first set of insights.</p>
          </div>
        </div>
      </section>
    );
  }

  const row = result.rows[0];
  const insights = row.insights_json;
  const date = new Date(row.created_at).toLocaleString();

  return (
    <section id="findings" className="tabpanel">
      <div className="kpis">
        <div className="kpi" style={{ gridColumn: 'span 4', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <small>AI Analysis Status</small>
            <b style={{ color: '#287a46', fontSize: 24, marginTop: 4, display: 'block' }}>Up to date</b>
          </div>
          <div style={{ textAlign: 'right', display: 'flex', alignItems: 'center', gap: '24px' }}>
            <div style={{ textAlign: 'right' }}>
              <small>Last Generated</small>
              <div style={{ color: 'var(--text-muted)', fontWeight: 500, marginTop: 4 }}>{date}</div>
            </div>
            <UpdateInsightsButton />
          </div>
        </div>
      </div>

      <div className="state-layout" style={{ gridTemplateColumns: '1fr 1fr 1fr', marginTop: 16 }}>
        <div className="panel">
          <div className="toolbar">Quote Structure</div>
          <div style={{ padding: '20px 24px' }}>
            <ul style={{ paddingLeft: 20, margin: 0, lineHeight: 1.7, color: 'var(--text-main)' }}>
              {insights.quote_structure?.map((bullet, i) => (
                <li key={i} style={{ marginBottom: 14 }}>{bullet}</li>
              ))}
            </ul>
          </div>
        </div>

        <div className="panel">
          <div className="toolbar">Types of Line Items</div>
          <div style={{ padding: '20px 24px' }}>
            <ul style={{ paddingLeft: 20, margin: 0, lineHeight: 1.7, color: 'var(--text-main)' }}>
              {insights.types_of_line_items?.map((bullet, i) => (
                <li key={i} style={{ marginBottom: 14 }}>{bullet}</li>
              ))}
            </ul>
          </div>
        </div>

        <div className="panel">
          <div className="toolbar">Pricing Structure Insights</div>
          <div style={{ padding: '20px 24px' }}>
            <ul style={{ paddingLeft: 20, margin: 0, lineHeight: 1.7, color: 'var(--text-main)' }}>
              {insights.pricing_structure_insights?.map((bullet, i) => (
                <li key={i} style={{ marginBottom: 14 }}>{bullet}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
