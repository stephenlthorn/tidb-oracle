'use client';

import { useState } from 'react';

export default function AskOracleWidget({ defaultQuestion = '' }) {
  const [question, setQuestion] = useState(defaultQuestion);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState([]);

  const onAsk = async () => {
    const q = question.trim();
    if (q.length < 2) { setError('Enter a question.'); return; }
    setLoading(true);
    setError('');
    setAnswer('');
    setCitations([]);
    try {
      const res = await fetch('/api/oracle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'oracle', message: q, top_k: 8 }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setAnswer(data.answer || 'No answer returned.');
      setCitations(data.citations || []);
    } catch (err) {
      setError(String(err?.message || err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Ask Oracle</span>
        <span className="tag tag-orange">Live</span>
      </div>
      <div className="panel-body" style={{ display: 'grid', gap: '0.65rem' }}>
        <textarea
          className="input"
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask any GTM or technical question..."
        />
        <div>
          <button className="btn btn-primary" onClick={onAsk} disabled={loading}>
            {loading ? 'Thinking...' : 'Ask Oracle →'}
          </button>
        </div>
        {error && <p className="error-text">{error}</p>}
        {answer && (
          <div className="answer-box">
            <p className="answer-text">{answer}</p>
            {citations.length > 0 && (
              <div className="answer-citations">
                <div className="citation-label">Evidence</div>
                <ul className="citation-list">
                  {citations.slice(0, 5).map((c, i) => (
                    <li key={i}>{c.title || c.source_id} {c.source_id ? `(${c.source_id})` : ''}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
