import React, { useEffect, useState } from 'react';
import { useConfigStore } from '../stores/useConfigStore';
import DynamicForm from './DynamicForm';
import { SchemaItem } from '../types/pywebview';

const StrategyConfigEditor: React.FC = () => {
    const { strategies, fetchStrategies, isLoading, error } = useConfigStore();
    const [selectedStrategy, setSelectedStrategy] = useState<string>('');
    const [schema, setSchema] = useState<SchemaItem[]>([]);
    const [config, setConfig] = useState<Record<string, any>>({});
    const [isSaving, setIsSaving] = useState(false);
    const [loadError, setLoadError] = useState<string | null>(null);

    useEffect(() => {
        fetchStrategies();
    }, [fetchStrategies]);

    useEffect(() => {
        if (strategies.length > 0 && !selectedStrategy) {
            setSelectedStrategy(strategies[0].name);
        }
    }, [strategies, selectedStrategy]);

    useEffect(() => {
        const loadConfig = async () => {
            if (!selectedStrategy) return;
            setLoadError(null);
            
            try {
                if (window.pywebview) {
                    const res = await window.pywebview.api.get_strategy_config(selectedStrategy);
                    if (res.success) {
                        setSchema(res.data.schema);
                        // Merge default with override for display
                        setConfig(res.data.merged);
                    } else {
                        setLoadError(res.error || 'Failed to load config');
                    }
                } else {
                    // Mock for dev
                    setSchema([
                        { key: 'rsi_period', type: 'number', label: 'RSI Period', default: 14, group: 'indicators', min: 1, step: 1 },
                        { key: 'oversold', type: 'number', label: 'Oversold Level', default: 30, group: 'indicators', min: 1, max: 100 }
                    ]);
                    setConfig({ rsi_period: 14, oversold: 30 });
                }
            } catch (err) {
                setLoadError(String(err));
            }
        };
        loadConfig();
    }, [selectedStrategy]);

    const handleSave = async (values: Record<string, any>) => {
        setIsSaving(true);
        try {
            if (window.pywebview) {
                const res = await window.pywebview.api.save_strategy_config(selectedStrategy, values);
                if (!res.success) {
                    alert(`Error saving: ${res.error}`);
                }
            } else {
                console.log('Mock save:', values);
                await new Promise(r => setTimeout(r, 1000));
            }
        } catch (err) {
            alert(`Error: ${err}`);
        } finally {
            setIsSaving(false);
        }
    };

    if (isLoading && strategies.length === 0) return <div>Loading strategies...</div>;
    if (error) return <div className="text-[var(--error)]">Error: {error}</div>;

    return (
        <div className="space-y-6">
            <div className="flex items-center space-x-4">
                <label className="text-sm font-medium text-[var(--text-secondary)]">Select Strategy:</label>
                <select 
                    value={selectedStrategy}
                    onChange={(e) => setSelectedStrategy(e.target.value)}
                    className="px-3 py-2 bg-[var(--bg-surface)] border border-[var(--border)] rounded-md focus:ring-1 focus:ring-[var(--accent)]"
                >
                    {strategies.map(s => (
                        <option key={s.name} value={s.name}>{s.display_name}</option>
                    ))}
                </select>
            </div>

            {loadError && (
                <div className="p-4 bg-[var(--error)]/10 text-[var(--error)] rounded-md border border-[var(--error)]/20">
                    {loadError}
                </div>
            )}

            {selectedStrategy && schema.length > 0 && (
                <div className="bg-[var(--bg-surface)] p-6 rounded-lg border border-[var(--border)] shadow-sm">
                    <h3 className="text-lg font-bold mb-6 border-b border-[var(--border)] pb-2">
                        Configuration: {strategies.find(s => s.name === selectedStrategy)?.display_name}
                    </h3>
                    <DynamicForm 
                        schema={schema}
                        initialValues={config}
                        onSubmit={handleSave}
                        isSaving={isSaving}
                    />
                </div>
            )}
        </div>
    );
};

export default StrategyConfigEditor;
