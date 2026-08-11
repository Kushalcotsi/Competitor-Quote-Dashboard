'use client';

export default function ExportButtons({ tableId, filename }) {
  const handlePrint = () => {
    window.print();
  };

  const handleExportCSV = () => {
    const table = document.getElementById(tableId);
    if (!table) {
      alert("Table not found to export.");
      return;
    }

    let csvContent = "data:text/csv;charset=utf-8,";
    const rows = table.querySelectorAll('tr');
    
    rows.forEach((row) => {
      const cols = row.querySelectorAll('th, td');
      const rowData = [];
      cols.forEach((col) => {
        // Clean up the data, escape quotes, remove line breaks
        let data = col.innerText || "";
        data = data.replace(/"/g, '""'); 
        data = data.replace(/(\r\n|\n|\r)/gm, " "); 
        rowData.push(`"${data.trim()}"`);
      });
      csvContent += rowData.join(",") + "\r\n";
    });

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `${filename}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div style={{ display: 'flex' }}>
      <button className="btn secondary" style={{ padding: '6px 12px', fontSize: 12, marginRight: 8 }} onClick={handlePrint}>Print / PDF</button>
      <button className="btn primary" style={{ padding: '6px 12px', fontSize: 12 }} onClick={handleExportCSV}>Export CSV</button>
    </div>
  );
}
