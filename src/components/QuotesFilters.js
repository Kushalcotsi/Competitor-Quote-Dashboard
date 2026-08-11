'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useState, useEffect } from 'react';

export default function QuotesFilters({ uniqueStates, uniqueCategories, uniqueSubcategories }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [state, setState] = useState(searchParams.get('state') || '');
  const [category, setCategory] = useState(searchParams.get('category') || '');
  const [subcategory, setSubcategory] = useState(searchParams.get('subcategory') || '');
  const [search, setSearch] = useState(searchParams.get('search') || '');

  useEffect(() => {
    const handler = setTimeout(() => {
      if (search !== (searchParams.get('search') || '')) {
        applyFilters(state, category, subcategory, search);
      }
    }, 400);
    return () => clearTimeout(handler);
  }, [search]);

  const applyFilters = (newState, newCategory, newSubcategory, newSearch) => {
    const params = new URLSearchParams(searchParams);
    if (newState) params.set('state', newState); else params.delete('state');
    if (newCategory) params.set('category', newCategory); else params.delete('category');
    if (newSubcategory) params.set('subcategory', newSubcategory); else params.delete('subcategory');
    if (newSearch) params.set('search', newSearch); else params.delete('search');
    
    router.push(`/?${params.toString()}`, { scroll: false });
  };

  const resetFilters = () => {
    setState('');
    setCategory('');
    setSubcategory('');
    setSearch('');
    const params = new URLSearchParams(searchParams);
    params.delete('state');
    params.delete('category');
    params.delete('subcategory');
    params.delete('search');
    router.push(`/?${params.toString()}`, { scroll: false });
  };

  return (
    <div className="grid" style={{ alignItems: 'center' }}>
      <div>
        <label>State</label>
        <select value={state} onChange={(e) => { setState(e.target.value); applyFilters(e.target.value, category, subcategory, search); }}>
          <option value="">All states</option>
          {uniqueStates.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div>
        <label>Category</label>
        <select value={category} onChange={(e) => { setCategory(e.target.value); applyFilters(state, e.target.value, subcategory, search); }}>
          <option value="">All categories</option>
          {uniqueCategories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div>
        <label>Subcategory</label>
        <select value={subcategory} onChange={(e) => { setSubcategory(e.target.value); applyFilters(state, category, e.target.value, search); }}>
          <option value="">All subcategories</option>
          {uniqueSubcategories.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <div>
        <label>Search Notes</label>
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
