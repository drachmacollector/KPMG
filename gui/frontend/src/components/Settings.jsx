/**
 * Settings.jsx
 *
 * Configuration screen — collects all settings needed to launch the pipeline.
 *
 * On mount: calls bridge.call('get_initial_state') to pre-populate every
 * field.  This is the fix for the previously-open bug where Pipeline Folder
 * was not auto-populated after MAHABOCW-Pipeline-Setup.exe had run.
 *
 * All browse actions call the Python Api's file-dialog methods so the OS
 * native pickers are used (pywebview delegates to the platform's dialog).
 *
 * Fields (mirrors the old SettingsScreen exactly):
 *   Pipeline Folder + Browse
 *   Python Interpreter + Browse + Test
 *   Input Excel File + Browse → auto-loads sheet names
 *   Sheet Name (combo, populated from workbook)
 *   Output Excel File + Save As
 *   Gemini API Key (password + show/hide toggle)
 *   Row Range (all | specific range with start/end spinners)
 *
 * Emits: onProceed(settingsDict) when validation passes and user clicks
 *   "Save & Continue".
 */
import { useEffect, useReducer, useState } from 'react';
import { call } from '../lib/bridge';

// ---------------------------------------------------------------------------
// Validation (mirrors SettingsScreen._validate() in the old settings_screen.py)
// ---------------------------------------------------------------------------
function validate(s) {
  const errors = [];
  if (!s.pipeline_dir) {
    errors.push('Pipeline folder is required.');
  }
  if (!s.python_exe) {
    errors.push('Python interpreter path is required.');
  }
  if (!s.input_file) {
    errors.push('Input Excel file is required.');
  }
  if (!s.sheet_name) {
    errors.push('Sheet name is required.');
  }
  if (!s.output_file) {
    errors.push('Output Excel file path is required.');
  }
  if (!s.gemini_api_key) {
    errors.push('Gemini API key is required.');
  }
  if (s.process_mode === 'range') {
    const start = parseInt(s.start_row, 10);
    const end   = parseInt(s.end_row,   10);
    if (isNaN(start) || isNaN(end)) {
      errors.push('Start and end row must be valid integers.');
    } else {
      if (start < 2) errors.push('Start row must be ≥ 2 (row 1 is the header).');
      if (end < start) errors.push('End row must be ≥ start row.');
    }
  }
  return errors;
}

// ---------------------------------------------------------------------------
// Default form state — filled in by get_initial_state() on mount
// ---------------------------------------------------------------------------
const DEFAULT_FORM = {
  pipeline_dir:   '',
  python_exe:     'python',
  input_file:     '',
  sheet_name:     '',
  output_file:    '',
  gemini_api_key: '',
  process_mode:   'all',
  start_row:      '2',
  end_row:        '100',
};

// Simple reducer so we can patch individual fields without full controlled boilerplate
function formReducer(state, patch) {
  return { ...state, ...patch };
}

export default function Settings({ onProceed }) {
  const [form,       dispatch]     = useReducer(formReducer, DEFAULT_FORM);
  const [sheets,     setSheets]    = useState([]);
  const [pyStatus,   setPyStatus]  = useState(null);   // {ok, version, error}
  const [errors,     setErrors]    = useState([]);
  const [saving,     setSaving]    = useState(false);
  const [showKey,    setShowKey]   = useState(false);
  const [loading,    setLoading]   = useState(true);

  // ------------------------------------------------------------------
  // On mount: pull initial state from Python
  // ------------------------------------------------------------------
  useEffect(() => {
    call('get_initial_state')
      .then(({ settings }) => {
        dispatch(settings);
        if (settings.input_file) {
          loadSheets(settings.input_file, settings.sheet_name);
        }
      })
      .catch(() => {/* non-fatal: form stays at defaults */})
      .finally(() => setLoading(false));
  }, []);

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------
  async function loadSheets(filePath, preferredSheet) {
    const names = await call('get_sheet_names', filePath);
    setSheets(names);
    if (names.length) {
      // Keep the saved sheet if it still exists, otherwise pick first
      dispatch({ sheet_name: names.includes(preferredSheet) ? preferredSheet : names[0] });
    }
  }

  async function browseFolder() {
    const path = await call('pick_pipeline_folder');
    if (path) dispatch({ pipeline_dir: path });
  }

  async function browseInputFile() {
    const path = await call('pick_input_file');
    if (path) {
      dispatch({ input_file: path });
      loadSheets(path, form.sheet_name);
    }
  }

  async function browseOutputFile() {
    const path = await call('pick_output_file');
    if (path) dispatch({ output_file: path });
  }

  async function browsePythonExe() {
    const path = await call('pick_python_exe');
    if (path) dispatch({ python_exe: path });
  }

  async function testPython() {
    setPyStatus(null);
    const result = await call('test_python', form.python_exe);
    setPyStatus(result);
  }

  async function handleSave() {
    const errs = validate(form);
    if (errs.length) { setErrors(errs); return; }
    setErrors([]);
    setSaving(true);
    try {
      await call('save_settings', form);
      onProceed(form);
    } finally {
      setSaving(false);
    }
  }

  // ------------------------------------------------------------------
  // Render helpers
  // ------------------------------------------------------------------
  function BrowseRow({ value, onChange, onBrowse, placeholder, readOnly }) {
    return (
      <div className="flex gap-2">
        <input
          className="field flex-1"
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          readOnly={readOnly}
        />
        <button className="btn whitespace-nowrap px-4" onClick={onBrowse} style={{ height: 38 }}>
          Browse…
        </button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full" style={{ background: 'var(--bg-base)' }}>
        <div className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading settings…</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--bg-base)' }}>
      {/* Accent top bar */}
      <div className="accent-bar" />

      {/* Header */}
      <div className="screen-header">
        <div className="accent-stripe" />
        <div>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#fff', letterSpacing: '-0.4px' }}>
            Configuration
          </div>
          <div className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
            Set up your pipeline before starting a run
          </div>
        </div>
        <div className="ml-auto pill">Step 1 of 2</div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 scroll-pane px-11 py-7 flex flex-col gap-5">

        {/* Error banner */}
        {errors.length > 0 && (
          <div
            className="rounded-xl p-4 text-sm"
            style={{
              background: 'var(--error-subtle)',
              border: '1px solid var(--error-border)',
              color: 'var(--error)',
              animation: 'fadeIn 0.3s both',
            }}
          >
            <div className="font-semibold mb-1">Please fix the following before continuing:</div>
            <ul className="list-disc list-inside space-y-0.5">
              {errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>
        )}

        {/* ── Pipeline group ── */}
        <div className="group-box">
          <div className="group-title">Pipeline</div>

          <div className="mb-4">
            <div className="section-label mb-2">Pipeline Folder</div>
            <BrowseRow
              value={form.pipeline_dir}
              onChange={v => dispatch({ pipeline_dir: v })}
              onBrowse={browseFolder}
              placeholder="Path to the folder containing verify_colleges.py"
            />
          </div>

          <div>
            <div className="section-label mb-2">Python Interpreter</div>
            <div className="flex gap-2">
              <input
                className="field flex-1"
                value={form.python_exe}
                onChange={e => dispatch({ python_exe: e.target.value })}
                placeholder='e.g. "python" or full path to python.exe'
              />
              <button className="btn px-4" style={{ height: 38 }} onClick={browsePythonExe}>Browse…</button>
              <button className="btn px-4" style={{ height: 38 }} onClick={testPython}>Test</button>
            </div>
            {pyStatus && (
              <div
                className="mt-1.5 text-xs pl-1"
                style={{ color: pyStatus.ok ? 'var(--success)' : 'var(--error)' }}
              >
                {pyStatus.ok ? `✓  ${pyStatus.version}` : `✗  ${pyStatus.error}`}
              </div>
            )}
          </div>
        </div>

        {/* ── Files group ── */}
        <div className="group-box">
          <div className="group-title">Files</div>

          <div className="mb-4">
            <div className="section-label mb-2">Input Excel File</div>
            <BrowseRow
              value={form.input_file}
              onChange={v => { dispatch({ input_file: v }); loadSheets(v, form.sheet_name); }}
              onBrowse={browseInputFile}
              placeholder="Select .xlsx input file"
            />
          </div>

          <div className="mb-4">
            <div className="section-label mb-2">Sheet Name</div>
            {sheets.length ? (
              <select
                className="field"
                value={form.sheet_name}
                onChange={e => dispatch({ sheet_name: e.target.value })}
                style={{ cursor: 'pointer' }}
              >
                {sheets.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            ) : (
              <input
                className="field"
                value={form.sheet_name}
                onChange={e => dispatch({ sheet_name: e.target.value })}
                placeholder="Select or type sheet name"
              />
            )}
          </div>

          <div>
            <div className="section-label mb-2">Output Excel File</div>
            <BrowseRow
              value={form.output_file}
              onChange={v => dispatch({ output_file: v })}
              onBrowse={browseOutputFile}
              placeholder="Select or create output .xlsx file"
            />
          </div>
        </div>

        {/* ── API Credentials group ── */}
        <div className="group-box">
          <div className="group-title">API Credentials</div>

          <div className="section-label mb-2">Gemini API Key</div>
          <div className="flex gap-2">
            <input
              className="field flex-1"
              type={showKey ? 'text' : 'password'}
              value={form.gemini_api_key}
              onChange={e => dispatch({ gemini_api_key: e.target.value })}
              placeholder="Paste your Gemini API key here"
            />
            <button
              className="btn px-4"
              style={{ height: 38, minWidth: 64 }}
              onClick={() => setShowKey(v => !v)}
            >
              {showKey ? 'Hide' : 'Show'}
            </button>
          </div>
          <p className="mt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
            ⓘ The key is stored in plaintext in your AppData folder.
            Contact your IT team if a more secure option is required.
          </p>
        </div>

        {/* ── Row Range group ── */}
        <div className="group-box">
          <div className="group-title">Row Range</div>

          <label className="flex items-center gap-3 mb-3 cursor-pointer">
            <input
              type="radio"
              name="process_mode"
              value="all"
              checked={form.process_mode === 'all'}
              onChange={() => dispatch({ process_mode: 'all' })}
              className="accent-accent w-4 h-4"
              style={{ accentColor: 'var(--accent)' }}
            />
            <span style={{ color: 'var(--text-primary)' }}>Process all rows</span>
          </label>

          <label className="flex items-center gap-3 mb-4 cursor-pointer">
            <input
              type="radio"
              name="process_mode"
              value="range"
              checked={form.process_mode === 'range'}
              onChange={() => dispatch({ process_mode: 'range' })}
              className="w-4 h-4"
              style={{ accentColor: 'var(--accent)' }}
            />
            <span style={{ color: 'var(--text-primary)' }}>Process a specific range</span>
          </label>

          {form.process_mode === 'range' && (
            <div className="flex gap-6 pl-7 mt-1">
              <div>
                <div className="section-label mb-1.5">Start row</div>
                <input
                  type="number"
                  className="field"
                  style={{ width: 120 }}
                  min={2}
                  value={form.start_row}
                  onChange={e => dispatch({ start_row: e.target.value })}
                />
              </div>
              <div>
                <div className="section-label mb-1.5">End row</div>
                <input
                  type="number"
                  className="field"
                  style={{ width: 120 }}
                  min={2}
                  value={form.end_row}
                  onChange={e => dispatch({ end_row: e.target.value })}
                />
              </div>
            </div>
          )}

          <p className="mt-3 text-xs" style={{ color: 'var(--text-muted)' }}>
            ⓘ Row numbers are 1-indexed and include the header row
            (row 2 is the first data row). Leave on 'all' to process the entire sheet.
          </p>
        </div>

        {/* Spacer + Save button */}
        <div className="flex justify-end pb-2">
          <button
            id="btn-save-continue"
            className="btn-primary px-8"
            style={{ height: 48, fontSize: 15, minWidth: 220 }}
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving…' : 'Save & Continue  →'}
          </button>
        </div>
      </div>
    </div>
  );
}
