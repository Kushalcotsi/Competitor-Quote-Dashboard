import Link from 'next/link';
import QuotesTable from '../components/QuotesTable';
import StateCoverage from '../components/StateCoverage';
import KeyFindings from '../components/KeyFindings';

export default async function Home(props) {
  const searchParams = await props.searchParams;
  const activeTab = searchParams?.tab || 'comparison';

  return (
    <main className="wrap">
      <section className="hero">
        <div>
          <div className="eyebrow">Competitive Pricing Intelligence</div>
          <h1>Competitor Quote Dashboard</h1>
          <p>Product hierarchy is now the primary reporting view, with state coverage moved after product size/subcategory. Data is fetched live from the `core` postgres schema.</p>
        </div>
        <div style={{ display: 'flex' }}>
          <button className="btn primary">Export CSV</button>
          <button className="btn secondary">Print / PDF</button>
        </div>
      </section>

      <nav className="tabs">
        <Link href="/?tab=comparison" className={`tab ${activeTab === 'comparison' ? 'active' : ''}`}>
          Quote Comparison
        </Link>
        <Link href="/?tab=states" className={`tab ${activeTab === 'states' ? 'active' : ''}`}>
          State Coverage
        </Link>
        <Link href="/?tab=findings" className={`tab ${activeTab === 'findings' ? 'active' : ''}`}>
          Key Findings
        </Link>
      </nav>

      {activeTab === 'comparison' && <QuotesTable searchParams={searchParams} />}
      {activeTab === 'states' && <StateCoverage searchParams={searchParams} />}
      {activeTab === 'findings' && <KeyFindings />}
    </main>
  );
}
