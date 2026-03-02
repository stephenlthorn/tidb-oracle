'use client';

import { useState } from 'react';

const SAMPLE_CURRENT_CUSTOMERS = `account,region,industry,current_platform,use_case,arr,renewal_date,notes
Evernorth Health,East,Healthcare,Aurora MySQL,Claims analytics + OLTP,$1.2M,2026-09-30,Needs legal + BAA confidence
Summit Retail,Central,Retail,Sharded MySQL,Inventory + checkout scaling,$640K,2026-11-15,CFO focused on 3-year TCO
Northwind Health,East,Healthcare,MySQL + Redshift,Unified HTAP reporting,$820K,2026-10-01,DBA adoption risk`;

const SAMPLE_PIPELINE = `account,region,stage,industry,workload,est_arr,close_quarter,competing_vendor,notes
Apex Logistics,Central,Technical Validation,Logistics,Routing + fleet telemetry,$550K,Q3 FY26,SingleStore,Needs benchmark proof
BlueLake Financial,East,POC,Financial Services,Fraud scoring + ledger reads,$900K,Q2 FY26,CockroachDB,Security review started
Horizon Media,East,Business Case,Media,Real-time campaign analytics,$700K,Q2 FY26,Aurora MySQL,Strong VP Eng sponsor`;

export default function MarketResearchWidget() {
  const [goal, setGoal] = useState('Market research on all current customers and pipeline, then build a strategic list for East and Central.');
  const [east, setEast] = useState(true);
  const [central, setCentral] = useState(true);
  const [currentCsv, setCurrentCsv] = useState('');
  const [pipelineCsv, setPipelineCsv] = useState('');
  const [additionalContext, setAdditionalContext] = useState('');
  const [topN, setTopN] = useState(8);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const fillSample = () => {
    setCurrentCsv(SAMPLE_CURRENT_CUSTOMERS);
    setPipelineCsv(SAMPLE_PIPELINE);
    setAdditionalContext(
      'Rep capacity: 2 AEs + 1 SE. Must-win goal: close two East opportunities this quarter while protecting top 3 renewals.'
    );
    setError('');
  };

  const generate = async () => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const regions = [];
      if (east) regions.push('East');
      if (central) regions.push('Central');
      const res = await fetch('/api/rep/market-research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategic_goal: goal,
          regions,
          current_customers_csv: currentCsv,
          pipeline_csv: pipelineCsv,
          additional_context: additionalContext,
          top_n: Number(topN) || 8,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || data?.error || 'Failed to generate strategy');
      setResult(data);
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Market Research Strategist</span>
        <span className="tag tag-orange">Sales Rep</span>
      </div>
      <div className="panel-body" style={{ display: 'grid', gap: '0.75rem' }}>
        <p style={{ color: 'var(--text-2)', fontSize: '0.78rem' }}>
          Use this to turn customer + pipeline data into an East/Central strategic execution list.
        </p>

        <div style={{ border: '1px solid var(--border)', borderRadius: '4px', padding: '0.6rem' }}>
          <div style={{ color: 'var(--text-3)', fontSize: '0.72rem', marginBottom: '0.45rem' }}>Input Checklist</div>
          <ul style={{ margin: 0, paddingLeft: '1rem', display: 'grid', gap: '0.2rem', color: 'var(--text-2)', fontSize: '0.75rem' }}>
            <li>Current customers CSV: account, region, industry, current_platform, use_case, arr</li>
            <li>Pipeline CSV: account, region, stage, industry, workload, est_arr, close_quarter, competing_vendor</li>
            <li>Strategic goal and optional context (team capacity, must-win deals, executive asks)</li>
          </ul>
        </div>

        <div style={{ display: 'grid', gap: '0.35rem' }}>
          <label htmlFor="strategy-goal" style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Strategic Goal</label>
          <textarea
            id="strategy-goal"
            className="input"
            rows={2}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
          />
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Territory Focus</span>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.76rem' }}>
            <input type="checkbox" checked={east} onChange={(e) => setEast(e.target.checked)} />
            East
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.76rem' }}>
            <input type="checkbox" checked={central} onChange={(e) => setCentral(e.target.checked)} />
            Central
          </label>
          <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.76rem' }}>
            Top N
            <input
              className="input"
              type="number"
              min={1}
              max={20}
              value={topN}
              onChange={(e) => setTopN(e.target.value)}
              style={{ width: '4.5rem' }}
            />
          </label>
        </div>

        <div className="two-col">
          <div style={{ display: 'grid', gap: '0.35rem' }}>
            <label htmlFor="current-customers" style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Current Customers CSV</label>
            <textarea
              id="current-customers"
              className="input"
              rows={8}
              value={currentCsv}
              onChange={(e) => setCurrentCsv(e.target.value)}
              placeholder="Paste CSV with required headers..."
            />
          </div>
          <div style={{ display: 'grid', gap: '0.35rem' }}>
            <label htmlFor="pipeline-csv" style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Pipeline CSV</label>
            <textarea
              id="pipeline-csv"
              className="input"
              rows={8}
              value={pipelineCsv}
              onChange={(e) => setPipelineCsv(e.target.value)}
              placeholder="Paste CSV with required headers..."
            />
          </div>
        </div>

        <div style={{ display: 'grid', gap: '0.35rem' }}>
          <label htmlFor="additional-context" style={{ color: 'var(--text-3)', fontSize: '0.72rem' }}>Additional Context (optional)</label>
          <textarea
            id="additional-context"
            className="input"
            rows={3}
            value={additionalContext}
            onChange={(e) => setAdditionalContext(e.target.value)}
            placeholder="Capacity constraints, must-win accounts, leadership asks, etc."
          />
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button className="btn" onClick={fillSample}>Load Sample Data</button>
          <button className="btn btn-primary" onClick={generate} disabled={loading}>
            {loading ? 'Generating…' : 'Generate Strategic List'}
          </button>
        </div>

        {error && <div className="error-text">{error}</div>}

        {result && (
          <div className="answer-box" style={{ display: 'grid', gap: '0.65rem' }}>
            <div className="answer-text">{result.summary}</div>

            {Array.isArray(result.required_inputs) && result.required_inputs.length > 0 && (
              <div>
                <div className="citation-label">Still Needed</div>
                <ul className="citation-list">
                  {result.required_inputs.map((item, idx) => <li key={idx}>{item}</li>)}
                </ul>
              </div>
            )}

            {Array.isArray(result.priority_accounts) && result.priority_accounts.length > 0 && (
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Account</th>
                      <th>Type</th>
                      <th>Region</th>
                      <th>Priority</th>
                      <th>Why Now</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.priority_accounts.map((item, idx) => (
                      <tr key={`${item.account}-${idx}`}>
                        <td className="row-title">{item.account}</td>
                        <td>{item.motion_type}</td>
                        <td>{item.region}</td>
                        <td style={{ color: item.priority === 'High' ? 'var(--accent)' : 'var(--text-2)' }}>{item.priority}</td>
                        <td style={{ minWidth: '360px' }}>
                          <div style={{ marginBottom: '0.3rem' }}>{item.why_now}</div>
                          {Array.isArray(item.actions) && item.actions.length > 0 && (
                            <div style={{ fontSize: '0.72rem', color: 'var(--text-3)' }}>
                              Next: {item.actions.slice(0, 2).join(' | ')}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {Array.isArray(result.execution_plan) && result.execution_plan.length > 0 && (
              <div>
                <div className="citation-label">Execution Plan</div>
                <ul className="citation-list">
                  {result.execution_plan.map((item, idx) => <li key={idx}>{item}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
