import React from "react";
import { LookbackInput } from "./LookbackInput";
import { PresetPills } from "./PresetPills";

export const RelativeTab: React.FC = () => {
  return (
    <div className="flex flex-col animate-in fade-in slide-in-from-top-1 duration-200">
      <LookbackInput />
      <div className="mt-1">
        <PresetPills />
      </div>
    </div>
  );
};
