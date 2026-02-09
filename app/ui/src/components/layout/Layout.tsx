import { ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';

interface LayoutProps {
  children: ReactNode;
  activeTab: string;
  onTabChange: (tab: string) => void;
  pageTitle?: string;
  isRunning?: boolean;
}

export function Layout({ 
  children, 
  activeTab, 
  onTabChange, 
  pageTitle,
  isRunning 
}: LayoutProps) {
  return (
    <div className="flex h-screen bg-[var(--color-bg)]">
      <Sidebar 
        activeTab={activeTab} 
        onTabChange={onTabChange}
        isRunning={isRunning}
      />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title={pageTitle} />
        
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
