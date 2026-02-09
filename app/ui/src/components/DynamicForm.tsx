import React, { useState, useEffect } from 'react';
import { SchemaItem } from '../types/pywebview';
import { Save } from 'lucide-react';

interface DynamicFormProps {
    schema: SchemaItem[];
    initialValues: Record<string, any>;
    onSubmit: (values: Record<string, any>) => void;
    isSaving?: boolean;
}

const DynamicForm: React.FC<DynamicFormProps> = ({ schema, initialValues, onSubmit, isSaving = false }) => {
    const [values, setValues] = useState<Record<string, any>>(initialValues);

    useEffect(() => {
        setValues(initialValues);
    }, [initialValues]);

    const handleChange = (key: string, value: any) => {
        setValues(prev => ({ ...prev, [key]: value }));
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSubmit(values);
    };

    // Group schema items
    const groups = schema.reduce((acc, item) => {
        const group = item.group || 'general';
        if (!acc[group]) acc[group] = [];
        acc[group].push(item);
        return acc;
    }, {} as Record<string, SchemaItem[]>);

    return (
        <form onSubmit={handleSubmit} className="space-y-8">
            {Object.entries(groups).map(([groupName, items]) => (
                <div key={groupName} className="border border-[var(--border)] rounded-lg p-6 bg-[var(--bg-secondary)]">
                    <h3 className="text-lg font-medium capitalize mb-4 text-[var(--accent)] border-b border-[var(--border)] pb-2">
                        {groupName}
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {items.map((item) => (
                            <div key={item.key} className="space-y-2">
                                <label className="block text-sm font-medium text-[var(--text-secondary)]">
                                    {item.label}
                                </label>
                                
                                {item.type === 'number' && (
                                    <input 
                                        type="number" 
                                        value={values[item.key] ?? ''}
                                        onChange={(e) => handleChange(item.key, parseFloat(e.target.value))}
                                        step={item.step}
                                        min={item.min}
                                        className="w-full px-3 py-2 bg-[var(--bg-surface)] border border-[var(--border)] rounded-md focus:ring-1 focus:ring-[var(--accent)] focus:border-[var(--accent)] outline-none transition-all"
                                    />
                                )}

                                {item.type === 'text' && (
                                    <input 
                                        type="text" 
                                        value={values[item.key] ?? ''}
                                        onChange={(e) => handleChange(item.key, e.target.value)}
                                        className="w-full px-3 py-2 bg-[var(--bg-surface)] border border-[var(--border)] rounded-md focus:ring-1 focus:ring-[var(--accent)] focus:border-[var(--accent)] outline-none transition-all"
                                    />
                                )}

                                {item.type === 'boolean' && (
                                    <div className="flex items-center h-10">
                                        <input 
                                            type="checkbox" 
                                            checked={!!values[item.key]}
                                            onChange={(e) => handleChange(item.key, e.target.checked)}
                                            className="w-5 h-5 text-[var(--accent)] rounded focus:ring-[var(--accent)] cursor-pointer"
                                        />
                                    </div>
                                )}
                                
                                {item.type === 'select' && (
                                    <select
                                        value={values[item.key] ?? ''}
                                        onChange={(e) => handleChange(item.key, e.target.value)}
                                        className="w-full px-3 py-2 bg-[var(--bg-surface)] border border-[var(--border)] rounded-md focus:ring-1 focus:ring-[var(--accent)] focus:border-[var(--accent)] outline-none transition-all"
                                    >
                                        {item.options?.map(opt => (
                                            <option key={opt} value={opt}>{opt}</option>
                                        ))}
                                    </select>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            ))}
            
            <div className="flex justify-end pt-4">
                <button 
                    type="submit" 
                    disabled={isSaving}
                    className="flex items-center space-x-2 px-6 py-2 bg-[var(--accent)] text-white rounded-md hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50"
                >
                    <Save className="w-4 h-4" />
                    <span>{isSaving ? 'Saving...' : 'Save Configuration'}</span>
                </button>
            </div>
        </form>
    );
};

export default DynamicForm;
