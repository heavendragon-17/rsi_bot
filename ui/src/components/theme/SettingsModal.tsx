import React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Settings as SettingsIcon, X } from "lucide-react";
import { ThemeSettings } from "./ThemeSettings";

interface SettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  open,
  onOpenChange,
}) => {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md bg-bg-secondary border-border-main p-6 shadow-2xl">
        <DialogHeader className="mb-4">
          <div className="flex items-center justify-between">
            <DialogTitle className="text-xl font-semibold text-text-primary flex items-center gap-2">
              <SettingsIcon size={20} className="text-accent-main" />
              Settings
            </DialogTitle>
            <DialogDescription className="sr-only">
              Adjust your theme and performance settings
            </DialogDescription>
          </div>
        </DialogHeader>

        <div className="custom-scrollbar overflow-y-auto max-h-[70vh] pr-2">
          <ThemeSettings />
        </div>
      </DialogContent>
    </Dialog>
  );
};
