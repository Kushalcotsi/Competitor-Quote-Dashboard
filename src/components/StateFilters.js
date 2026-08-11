'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useState, useEffect } from 'react';

export default function StateFilters({ uniqueStates, uniqueCompetitors, uniqueCategories }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [state, setState] = useState(searchParams.get('state') || '');
  const [competitor, setCompetitor] = useState(searchParams.get('competitor') || '');
  const [category, setCategory] = useState(searchParams.get('category') || '');
  const [search, setSearch] = useState(searchParams.get('search') || '');

  useEffect(() => {
    const handler = setTimeout(() => {
      if (search !== (searchParams.get('search') || '')) {
        applyFilters(state, competitor, category, search);
      }
    }, 400);
    return () => clearTimeout(handler);
  }, [search]);

  const applyFilters = (newState, newCompetitor, newCategory, newSearch) => {
    const params = new URLSearchParams(searchParams);
    if (newState) params.set('state', newState); else params.delete('state');
    if (newCompetitor) params.set('competitor', newCompetitor); else params.delete('competitor');
    if (newCategory) params.set('category', newCategory); else params.delete('category');
    if (newSearch) params.set('search', newSearch); else params.delete('search');
    
    router.push(`/?${params.toString()}`, { scroll: false });
  };

  const resetFilters = () => {
    setState('');
    setCompetitor('');
    setCategory('');
    setSearch('');
    const params = new URLSearchParams(searchParams);
    params.delete('state');
    params.delete('competitor');
    params.delete('category');
    params.delete('search');
    router.push(`/?${params.toString()}`, { scroll: false });
  };

  return (
    <div className="grid" style={{ alignItems: 'center' }}>
      <div>
        <label>State</label>
        <select value={state} onChange={(e) => { setState(e.target.value); applyFilters(e.target.value, competitor, category, search); }}>
          <option value="">All states</option>
          {uniqueStates.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div>
        <label>Competitor</label>
        <select value={competitor} onChange={(e) => { setCompetitor(e.target.value); applyFilters(state, e.target.value, category, search); }}>
          <option value="">All competitors</option>
          {uniqueCompetitors.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div>
        <label>Category</label>
        <select value={category} onChange={(e) => { setCategory(e.target.value); applyFilters(state, competitor, e.target.value, search); }}>
          <option value="">All categories</option>
          {uniqueCategories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div>
        <label>Search Data</label>
        <input 
          placeholder="Keywords..." 
          value={search} 
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <button className="btn secondary" onClick={resetFilters}>Reset</button>
    </div>
  );
}
