import React from 'react';
import { MatchRecap } from '../types';
import { X, Award, FileText, CheckCircle2, ChevronRight } from 'lucide-react';

interface RecapModalProps {
  recap: MatchRecap | null;
  isOpen: boolean;
  onClose: () => void;
  isLoading: boolean;
}

export const RecapModal: React.FC<RecapModalProps> = ({
  recap,
  isOpen,
  onClose,
  isLoading,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="relative w-full max-w-3xl bg-[#0e1320] border border-slate-700 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 bg-gradient-to-r from-[#38003c] via-[#1a2238] to-[#0e1320] border-b border-slate-700">
          <div className="flex items-center space-x-2">
            <FileText className="w-5 h-5 text-emerald-400" />
            <h3 className="font-display font-bold text-lg text-white uppercase tracking-wider">
              Premier League Studio Match Intelligence Recap
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6">
          {isLoading ? (
            <div className="py-16 flex flex-col items-center justify-center space-y-3 text-slate-400">
              <div className="w-8 h-8 border-3 border-emerald-400 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm font-mono">Synthesizing match intelligence with Azure OpenAI...</p>
            </div>
          ) : recap ? (
            <>
              {/* Title & Headline */}
              <div className="border-b border-slate-800 pb-4">
                <span className="text-xs font-mono font-bold text-emerald-400 uppercase tracking-widest block mb-1">
                  OFFICIAL STUDIO BULLETIN • GENERATED AT {recap.generated_at_clock}
                </span>
                <h2 className="font-display font-extrabold text-2xl text-white tracking-wide">
                  {recap.headline}
                </h2>
                <p className="text-xs text-slate-400 font-mono mt-1">
                  {recap.control_vs_chaos_summary}
                </p>
              </div>

              {/* Summary Paragraphs */}
              <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  EXECUTIVE SUMMARY
                </h4>
                {recap.summary_paragraphs.map((para, idx) => (
                  <p key={idx} className="text-sm text-slate-300 leading-relaxed">
                    {para}
                  </p>
                ))}
              </div>

              {/* Tactical Breakdown */}
              <div className="bg-slate-950/80 rounded-xl p-4 border border-slate-800/80 space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-400">
                  TACTICAL DECONSTRUCTION
                </h4>
                <ul className="space-y-2">
                  {recap.tactical_breakdown.map((item, idx) => (
                    <li key={idx} className="flex items-start space-x-2 text-xs text-slate-300">
                      <ChevronRight className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Turning Points Grid & Player of the Match */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Turning Points */}
                <div className="bg-slate-950/80 rounded-xl p-4 border border-slate-800/80 space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400">
                    KEY TURNING POINTS
                  </h4>
                  <div className="space-y-1.5 font-mono text-xs text-slate-300">
                    {recap.key_turning_points.map((tp, idx) => (
                      <div key={idx} className="p-2 rounded bg-slate-900 border border-slate-800/60">
                        {tp}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Player of the Match */}
                <div className="bg-gradient-to-br from-slate-950 to-emerald-950/30 rounded-xl p-4 border border-emerald-500/30 flex flex-col justify-center items-center text-center space-y-2">
                  <Award className="w-8 h-8 text-amber-400 animate-bounce" />
                  <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-400">
                    STUDIO PLAYER OF THE MATCH
                  </span>
                  <h3 className="font-display font-extrabold text-xl text-white tracking-wide">
                    {recap.player_of_the_match}
                  </h3>
                  <p className="text-xs text-slate-400">
                    Outstanding influence across progressive ball movement, high press evasion, and threat creation.
                  </p>
                </div>
              </div>
            </>
          ) : null}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 bg-slate-950 border-t border-slate-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg transition"
          >
            Close Recap
          </button>
        </div>
      </div>
    </div>
  );
};
