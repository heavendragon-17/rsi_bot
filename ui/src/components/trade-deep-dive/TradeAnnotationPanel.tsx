import React, { useState, useEffect } from "react";
import {
  Star,
  AlertTriangle,
  BookOpen,
  Lightbulb,
  Clover,
  Skull,
  type LucideIcon,
} from "lucide-react";
import { useExportStore } from "../../stores/exportStore";
import type { TradeTag } from "../../stores/exportStore";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";

interface TradeAnnotationPanelProps {
  tradeId: number;
}

const ALL_TAGS: TradeTag[] = [
  "star",
  "review",
  "learning",
  "idea",
  "lucky",
  "unlucky",
];

const TAG_ICONS: Record<TradeTag, LucideIcon> = {
  star: Star,
  review: AlertTriangle,
  learning: BookOpen,
  idea: Lightbulb,
  lucky: Clover,
  unlucky: Skull,
};

const TAG_COLORS: Record<TradeTag, string> = {
  star: "text-yellow-400 border-yellow-400/30 bg-yellow-400/10",
  review: "text-orange-400 border-orange-400/30 bg-orange-400/10",
  learning: "text-blue-400 border-blue-400/30 bg-blue-400/10",
  idea: "text-purple-400 border-purple-400/30 bg-purple-400/10",
  lucky: "text-green-400 border-green-400/30 bg-green-400/10",
  unlucky: "text-red-400 border-red-400/30 bg-red-400/10",
};

const TAG_INACTIVE = "text-slate-500 border-slate-600/30 bg-slate-800/30";

export function TradeAnnotationPanel({ tradeId }: TradeAnnotationPanelProps) {
  const { annotations, addAnnotation, updateAnnotation } = useExportStore();
  const annotation = annotations[tradeId];

  const [note, setNote] = useState(annotation?.note ?? "");
  const [tags, setTags] = useState<TradeTag[]>(annotation?.tags ?? []);

  // Sync when tradeId changes (navigating between trades)
  useEffect(() => {
    setNote(annotation?.note ?? "");
    setTags(annotation?.tags ?? []);
  }, [tradeId]);

  const debouncedNote = useDebouncedValue(note, 600);

  // Auto-save when debounced note or tags change
  useEffect(() => {
    if (debouncedNote === (annotation?.note ?? "") && tags === (annotation?.tags ?? [])) return;
    if (annotation) {
      updateAnnotation(tradeId, debouncedNote, tags);
    } else if (debouncedNote || tags.length > 0) {
      addAnnotation(tradeId, debouncedNote, tags);
    }
  }, [debouncedNote, tags]);

  function toggleTag(tag: TradeTag) {
    setTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );
  }

  return (
    <div className="bg-slate-900/50 rounded-xl p-5 border border-white/10">
      <h3 className="text-white font-bold text-sm mb-4">Annotation</h3>

      {/* Tag toggles */}
      <div className="flex flex-wrap gap-2 mb-4">
        {ALL_TAGS.map((tag) => {
          const Icon = TAG_ICONS[tag];
          const isActive = tags.includes(tag);
          return (
            <button
              key={tag}
              onClick={() => toggleTag(tag)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                isActive ? TAG_COLORS[tag] : TAG_INACTIVE
              }`}
            >
              <Icon size={12} />
              {tag.charAt(0).toUpperCase() + tag.slice(1)}
            </button>
          );
        })}
      </div>

      {/* Notes textarea */}
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Add a note about this trade..."
        rows={3}
        className="w-full bg-slate-800/60 border border-white/10 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 resize-none focus:outline-none focus:border-violet-500/50 transition-colors"
      />
      <p className="text-xs text-slate-500 mt-1">Auto-saves as you type</p>
    </div>
  );
}
