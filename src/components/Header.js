export default function Header() {
  return (
    <section className="hero">
      <div className="eyebrow">Competitive Pricing Intelligence</div>
      <h1>Competitor Quote Dashboard</h1>
      <p>
        Product hierarchy is now the primary reporting view, with state coverage
        moved after product size/subcategory. State Coverage includes category,
        subcategory, and rate range. Key Findings include drill-down quote
        examples behind each insight.
      </p>
      <button className="btn primary" id="exportCompare">
        Export filtered comparison CSV
      </button>
      <button className="btn secondary" onClick={() => window.print()}>
        Print / Save PDF
      </button>
    </section>
  );
}
