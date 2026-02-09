import { useState, useEffect } from 'react';
import { Save, RefreshCw } from 'lucide-react';
import { useToast } from '../common/index';

export function GlobalConfigForm() {
  const { addToast } = useToast();
  const [config, setConfig] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    setLoading(true);
    try {
      // In a real app, this would call an API
      // Since we don't have a direct 'get_config' yet in main_ui.py (only for specific strategies),
      // we'll mock it or assume it's exposed. 
      // For MVP, we will simulate loading the global config file content.
      if (window.pywebview) {
          const res = await window.pywebview.api.read_file('config.yaml');
          if (res.success) {
            setConfig(res.data);
          } else {
            addToast('error', 'Failed to load config');
          }
      }
    } catch (e) {
      addToast('error', 'Error loading config');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (window.pywebview) {
        const res = await window.pywebview.api.save_file('config.yaml', config);
        if (res.success) {
          addToast('success', 'Configuration saved successfully');
        } else {
          addToast('error', 'Failed to save configuration');
        }
      }
    } catch (e) {
      addToast('error', 'Error saving config');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 p-4 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg h-full">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium text-[var(--color-text)]">Global Configuration</h3>
          <p className="text-sm text-[var(--color-text-muted)]">
            Edit `config.yaml` directly. Be careful with syntax.
          </p>
        </div>
        <div className="flex gap-2">
            <button
                onClick={loadConfig}
                disabled={loading}
                className="p-2 text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-hover)] rounded transition-colors"
                title="Refresh"
            >
                <RefreshCw size={20} className={loading ? 'animate-spin' : ''} />
            </button>
            <button
                onClick={handleSave}
                disabled={saving || loading}
                className="flex items-center gap-2 px-4 py-2 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded transition-colors disabled:opacity-50"
            >
                <Save size={18} />
                {saving ? 'Saving...' : 'Save Changes'}
            </button>
        </div>
      </div>

      <div className="flex-1 min-h-[400px]">
        <textarea
          value={config}
          onChange={(e) => setConfig(e.target.value)}
          className="w-full h-full p-4 font-mono text-sm bg-[var(--color-bg)] text-[var(--color-text)] border border-[var(--color-border)] rounded focus:border-[var(--color-primary)] outline-none resize-none"
          spellCheck={false}
        />
      </div>
    </div>
  );
}
