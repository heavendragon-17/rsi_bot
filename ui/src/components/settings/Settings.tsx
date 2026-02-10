import React from 'react';
import { ThemeSelector } from './ThemeSelector';
import { GlobalConfigForm } from './GlobalConfigForm';

export const Settings: React.FC = () => {
  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <h2 className="text-xl font-bold text-text">Settings</h2>

      <GlobalConfigForm />

      <ThemeSelector />

      <div className="bg-surface border border-border rounded-xl p-6 text-center">
        <p className="text-text-muted text-sm">
          RSI Bot Backtest UI v1.0.0
        </p>
      </div>
    </div>
  );
};
