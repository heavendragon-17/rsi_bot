import React from 'react';
import { ParameterSchema } from '../../types/pywebview';
import { Select } from './Select';

interface DynamicFormProps {
  schema: ParameterSchema[];
  values: Record<string, any>;
  onChange: (key: string, value: any) => void;
  className?: string;
}

export const DynamicForm: React.FC<DynamicFormProps> = ({
  schema,
  values,
  onChange,
  className = ""
}) => {
  const groupedSchema = schema.reduce((acc, field) => {
    const group = field.group || 'general';
    if (!acc[group]) acc[group] = [];
    acc[group].push(field);
    return acc;
  }, {} as Record<string, ParameterSchema[]>);

  return (
    <div className={`space-y-8 ${className}`}>
      {Object.entries(groupedSchema).map(([group, fields]) => (
        <div key={group} className="space-y-4">
          <div className="flex items-center gap-2 mb-4 pb-2 border-b border-border/50">
            <h3 className="text-xs font-bold text-primary uppercase tracking-wider">
              {group} Settings
            </h3>
            <span className="text-xs text-text-muted bg-surface-hover px-2 rounded-full">
              {fields.length}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-6">
            {fields.map((field) => (
              <div key={field.key} className="flex flex-col space-y-1.5 group relative">
                <div className="flex justify-between items-center">
                  <label className="text-sm font-medium text-text group-hover:text-primary transition-colors">
                    {field.label}
                  </label>
                  {field.type === 'number' && (
                    <span className="text-[10px] text-text-muted font-mono bg-surface-hover px-1 rounded opacity-0 group-hover:opacity-100 transition-opacity">
                      {field.min} - {field.max}
                    </span>
                  )}
                </div>

                {field.type === 'number' && (
                  <input
                    type="number"
                    value={values[field.key] ?? ''}
                    min={field.min}
                    max={field.max}
                    step={field.step || 'any'}
                    onChange={(e) => onChange(field.key, parseFloat(e.target.value))}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all hover:border-primary/50"
                  />
                )}

                {field.type === 'select' && (
                  <Select
                    options={field.options?.map(opt => ({ value: opt, label: opt })) || []}
                    value={values[field.key] ?? ''}
                    onChange={(e) => onChange(field.key, e.target.value)}
                    className="w-full"
                  />
                )}

                {field.type === 'boolean' && (
                  <label className="flex items-center gap-3 cursor-pointer h-10 p-2 border border-border rounded-lg hover:border-primary/50 transition-colors bg-surface">
                    <input
                      type="checkbox"
                      checked={!!values[field.key]}
                      onChange={(e) => onChange(field.key, e.target.checked)}
                      className="w-4 h-4 rounded border-border text-primary focus:ring-primary accent-primary"
                    />
                    <span className="text-sm text-text-muted select-none">
                      {values[field.key] ? 'Enabled' : 'Disabled'}
                    </span>
                  </label>
                )}

                {field.description && (
                  <p className="text-xs text-text-muted mt-1 leading-relaxed opacity-80 group-focus-within:opacity-100 group-hover:opacity-100 transition-opacity">
                    {field.description}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};
