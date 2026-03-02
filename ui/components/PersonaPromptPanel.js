'use client';

import { useMemo, useState } from 'react';

const PERSONAS = [
  {
    id: 'sales_representative',
    label: 'Sales Representative',
    defaultPrompt:
      'Prioritize deal progression. Provide concise next steps, discovery questions, and follow-up messaging suggestions tied to account priorities.',
  },
  {
    id: 'marketing_specialist',
    label: 'Marketing Specialist',
    defaultPrompt:
      'Prioritize positioning and pipeline generation. Recommend campaign angles, content hooks, and measurable GTM actions aligned to persona and industry.',
  },
  {
    id: 'se',
    label: 'SE',
    defaultPrompt:
      'Prioritize technical validation. Focus on architecture fit, migration risks, POC design, and concrete technical proof points for the workload.',
  },
];

const PERSONA_IDS = new Set(PERSONAS.map((persona) => persona.id));

function defaultPromptFor(personaId) {
  return PERSONAS.find((persona) => persona.id === personaId)?.defaultPrompt || PERSONAS[0].defaultPrompt;
}

export default function PersonaPromptPanel({ initialPersona = 'sales_representative', initialPrompt = '' }) {
  const safeInitialPersona = PERSONA_IDS.has(initialPersona) ? initialPersona : 'sales_representative';
  const [persona, setPersona] = useState(safeInitialPersona);
  const [prompt, setPrompt] = useState(initialPrompt?.trim() || defaultPromptFor(safeInitialPersona));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  const defaultPrompt = useMemo(() => defaultPromptFor(persona), [persona]);

  const handlePersonaChange = (event) => {
    const nextPersona = event.target.value;
    setPersona(nextPersona);
    setPrompt(defaultPromptFor(nextPersona));
    setMessage('');
  };

  const resetPrompt = () => {
    setPrompt(defaultPrompt);
    setMessage('Default prompt restored for this persona.');
  };

  const save = async () => {
    setSaving(true);
    setMessage('');
    try {
      const res = await fetch('/api/admin/kb-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          persona_name: persona,
          persona_prompt: prompt,
        }),
      });
      if (!res.ok) throw new Error('Failed to save persona prompt');
      setMessage('Saved.');
    } catch {
      setMessage('Could not save persona prompt.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Persona Prompt</span>
      </div>
      <div className="panel-body" style={{ display: 'grid', gap: '0.75rem' }}>
        <p style={{ color: 'var(--text-2)', fontSize: '0.8rem' }}>
          This prompt guides Ask Oracle and call coaching responses.
        </p>

        <div style={{ display: 'grid', gap: '0.35rem' }}>
          <label htmlFor="persona-select" style={{ color: 'var(--text-3)', fontSize: '0.74rem' }}>
            Persona
          </label>
          <select
            id="persona-select"
            className="input"
            value={persona}
            onChange={handlePersonaChange}
            aria-label="Select persona"
          >
            {PERSONAS.map((personaOption) => (
              <option key={personaOption.id} value={personaOption.id}>
                {personaOption.label}
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: 'grid', gap: '0.35rem' }}>
          <label htmlFor="persona-prompt" style={{ color: 'var(--text-3)', fontSize: '0.74rem' }}>
            Prompt
          </label>
          <textarea
            id="persona-prompt"
            className="input"
            rows={5}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Customize how Oracle responds for this persona."
            aria-label="Persona prompt"
          />
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save Persona Prompt'}
          </button>
          <button type="button" className="btn" onClick={resetPrompt}>
            Use Persona Default
          </button>
        </div>

        {message && (
          <div style={{ color: message === 'Saved.' ? 'var(--success)' : 'var(--text-2)', fontSize: '0.76rem' }}>
            {message}
          </div>
        )}
      </div>
    </div>
  );
}
