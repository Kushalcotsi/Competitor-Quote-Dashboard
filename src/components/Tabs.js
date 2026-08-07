export default function Tabs({ activeTab, setActiveTab }) {
  const tabs = [
    { id: 'comparison', label: 'Quote Comparison' },
    { id: 'states', label: 'State Coverage' },
    { id: 'findings', label: 'Key Findings' }
  ];

  return (
    <nav className="tabs-container">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
          onClick={() => setActiveTab(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
