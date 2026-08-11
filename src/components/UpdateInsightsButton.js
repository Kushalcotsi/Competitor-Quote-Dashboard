'use client';

import { useState } from 'react';
import { updateAIInsights } from '../app/actions';

export default function UpdateInsightsButton() {
  const [loading, setLoading] = useState(false);

  const handleUpdate = async () => {
    setLoading(true);
    const result = await updateAIInsights();
    setLoading(false);
    
    if (!result.success) {
      alert('Failed to update insights: ' + result.error);
    }
  };

  return (
    <button 
      className="btn primary" 
      onClick={handleUpdate} 
      disabled={loading}
      style={{
        padding: '10px 20px',
        fontSize: '14px',
        fontWeight: 'bold',
        opacity: loading ? 0.7 : 1,
        cursor: loading ? 'not-allowed' : 'pointer'
      }}
    >
      {loading ? 'Analyzing Data... ⏳' : 'Sync Latest Data'}
    </button>
  );
}
