import React from "react";
import { Navbar } from "./Navbar";
import { Sidebar } from "./Sidebar";
import { MobileNav } from "./MobileNav";
import { MobileSidebarSheet } from "./MobileSidebarSheet";
import { useBacktestStore } from "../../stores/backtestStore";
import { cn } from "../../lib/utils";

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { isSidebarOpen, mode } = useBacktestStore();
  
  return (
    <div className="min-h-screen bg-bg-primary text-text-primary font-sans selection:bg-accent-main/30">
      <Navbar />
      
      <div className="pt-20 px-2 sm:px-4 pb-20 lg:pb-4 flex gap-2 sm:gap-4 h-[calc(100vh)]">
        {/* Spacer for fixed sidebar - hidden on mobile */}
        <div 
          className={cn(
            "shrink-0 transition-all duration-300 ease-in-out hidden lg:block", 
            isSidebarOpen ? "w-[320px]" : "w-[60px]"
          )} 
        />
        
        {/* Desktop Sidebar - hidden on mobile */}
        <div className="hidden lg:block">
          <Sidebar />
        </div>
        
        {/* Mobile Sidebar Sheet */}
        <MobileSidebarSheet />
        
        <main className={cn(
          "flex-1 rounded-xl border border-border-main bg-bg-surface/40 backdrop-blur-sm relative transition-all duration-300",
          mode === "settings" ? "overflow-y-auto custom-scrollbar" : "overflow-hidden"
        )}>
          {children}
        </main>
      </div>
      
      {/* Mobile Bottom Navigation */}
      <MobileNav />
    </div>
  );
};