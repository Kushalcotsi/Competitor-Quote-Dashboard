export default function KpiCard({ title, value, icon: Icon }) {
  return (
    <div className="card kpi-card">
      <div className="kpi-header">
        <span>{title}</span>
        {Icon && (
          <div className="kpi-icon">
            <Icon size={18} />
          </div>
        )}
      </div>
      <div className="kpi-value">{value}</div>
    </div>
  );
}
