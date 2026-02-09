import React from 'react';
import { ParameterSchema } from '../../types/pywebview';

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
    <div className={`space-y-6 ${className}`}>
      {Object.entries(groupedSchema).map(([group, fields]) => (
        <div key={group} className="space-y-4">
          <h3 className="text-sm font-semibold text-text-muted uppercase tracking-wider">
            {group}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {fields.map((field) => (
              <div key={field.key} className="flex flex-col space-y-1">
                <label className="text-sm font-medium text-text">
                  {field.label}
                </label>

                {field.type === 'number' && (
                  <input
                    type="number"
                    value={values[field.key] ?? ''}
                    min={field.min}
                    max={field.max}
                    step={field.step || 'any'}
                    onChange={(e) => onChange(field.key, parseFloat(e.target.value))}
                    className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary focus:border-primary outline-none"
                  />
                )}

                {field.type === 'select' && (
                  <select
                    value={values[field.key] ?? ''}
                    onChange={(e) => onChange(field.key, e.target.value)}
                    className="bg-surface border border-border rounded-md px-3 py-2 text-text focus:ring-1 focus:ring-primary focus:border-primary outline-none appearance-none"
                  >
                    {field.options?.map((opt) => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                )}

                {field.type === 'boolean' && (
                  <div className="flex items-center h-10">
                    <input
                      type="checkbox"
                      checked={!!values[field.key]}
                      onChange={(e) => onChange(field.key, e.target.checked)}
                      className="w-5 h-5 rounded border-border bg-surface text-primary focus:ring-primary"
                    />
                  </div>
                )}

                {field.description && (
                  <p className="text-xs text-text-muted">{field.description}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};
