import { useState } from "react";
import {
  LayoutDashboard, Star, Target, Map, GitBranch, MessageSquare,
  BarChart3, CheckSquare, Bell, Search, Settings, TrendingUp,
  TrendingDown, AlertTriangle, Bot, UserCheck, Clock, MoreHorizontal,
  Filter, Plus, Award, Check, X, Sparkles, Activity, Calendar,
  ChevronDown, ChevronRight, Briefcase, Zap, Eye,
} from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

// ─── Constants ───────────────────────────────────────────────────────────────
const PRIMARY = "#5B5BD6";
const AI_GREEN = "#00B87C";
const AI_AMBER = "#F59E0B";
const AI_RED = "#EF4444";

type NavSection = "dashboard" | "reviews" | "goals" | "career" | "succession" | "feedback" | "analytics" | "approvals";

// ─── Shared UI ────────────────────────────────────────────────────────────────

function AIBadge({ score }: { score: number }) {
  const color = score >= 80 ? AI_GREEN : score >= 60 ? AI_AMBER : AI_RED;
  const label = score >= 80 ? "High" : score >= 60 ? "Med" : "Low";
  return (
    <div className="flex items-center gap-1.5">
      <Bot size={10} style={{ color }} />
      <div className="w-12 h-1 rounded-full overflow-hidden bg-black/10">
        <div className="h-full rounded-full" style={{ width: `${score}%`, backgroundColor: color }} />
      </div>
      <span className="text-[10px] font-medium" style={{ color, fontFamily: "DM Mono, monospace" }}>
        {label} {score}%
      </span>
    </div>
  );
}

const STATUS_MAP: Record<string, { pill: string; dot: string }> = {
  "Approved":      { pill: "bg-emerald-50 text-emerald-700 border-emerald-100", dot: "bg-emerald-500" },
  "Pending Review":{ pill: "bg-amber-50 text-amber-700 border-amber-100",       dot: "bg-amber-500"   },
  "AI Draft":      { pill: "bg-violet-50 text-violet-700 border-violet-100",    dot: "bg-violet-500"  },
  "In Progress":   { pill: "bg-blue-50 text-blue-700 border-blue-100",          dot: "bg-blue-500"    },
  "Overdue":       { pill: "bg-red-50 text-red-700 border-red-100",             dot: "bg-red-500"     },
  "Calibrating":   { pill: "bg-indigo-50 text-indigo-700 border-indigo-100",    dot: "bg-indigo-500"  },
  "On Track":      { pill: "bg-emerald-50 text-emerald-700 border-emerald-100", dot: "bg-emerald-500" },
  "At Risk":       { pill: "bg-amber-50 text-amber-700 border-amber-100",       dot: "bg-amber-500"   },
  "Behind":        { pill: "bg-red-50 text-red-700 border-red-100",             dot: "bg-red-500"     },
  "Not Started":   { pill: "bg-neutral-100 text-neutral-500 border-neutral-200",dot: "bg-neutral-400" },
  "Complete":      { pill: "bg-emerald-50 text-emerald-700 border-emerald-100", dot: "bg-emerald-500" },
  "Critical":      { pill: "bg-red-50 text-red-700 border-red-100",             dot: "bg-red-500"     },
  "Elevated":      { pill: "bg-amber-50 text-amber-700 border-amber-100",       dot: "bg-amber-500"   },
  "Nominated":     { pill: "bg-neutral-100 text-neutral-500 border-neutral-200",dot: "bg-neutral-400" },
  "Ready Now":     { pill: "bg-emerald-50 text-emerald-700 border-emerald-100", dot: "bg-emerald-500" },
  "Ready 1-2yr":   { pill: "bg-blue-50 text-blue-700 border-blue-100",          dot: "bg-blue-500"    },
  "Low":           { pill: "bg-emerald-50 text-emerald-700 border-emerald-100", dot: "bg-emerald-500" },
  "Medium":        { pill: "bg-amber-50 text-amber-700 border-amber-100",       dot: "bg-amber-500"   },
  "High":          { pill: "bg-red-50 text-red-700 border-red-100",             dot: "bg-red-500"     },
  "Rejected":      { pill: "bg-red-50 text-red-700 border-red-100",             dot: "bg-red-500"     },
};

function Chip({ status }: { status: string }) {
  const s = STATUS_MAP[status] ?? { pill: "bg-neutral-100 text-neutral-500 border-neutral-200", dot: "bg-neutral-400" };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium border ${s.pill}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${s.dot}`} />
      {status}
    </span>
  );
}

function Av({ name, size = "sm" }: { name: string; size?: "xs" | "sm" | "md" }) {
  const initials = name.split(" ").slice(0, 2).map(n => n[0]).join("");
  const palette = ["#5B5BD6","#00B87C","#F59E0B","#EF4444","#06B6D4","#8B5CF6","#EC4899","#0EA5E9"];
  const bg = palette[name.charCodeAt(0) % palette.length];
  const sz = { xs: "w-6 h-6 text-[9px]", sm: "w-7 h-7 text-[10px]", md: "w-9 h-9 text-sm" }[size];
  return (
    <div className={`${sz} rounded-full flex items-center justify-center font-semibold text-white flex-shrink-0`} style={{ backgroundColor: bg }}>
      {initials}
    </div>
  );
}

function KPI({ label, value, sub, trend, up }: { label: string; value: string; sub?: string; trend?: string; up?: boolean }) {
  return (
    <div className="bg-white rounded-xl border border-black/[0.06] p-4 flex flex-col gap-2.5 hover:border-black/10 transition-colors">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-neutral-400">{label}</span>
        {trend && (
          <div className={`flex items-center gap-0.5 text-[11px] font-medium ${up ? "text-emerald-600" : "text-red-500"}`}>
            {up ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
            {trend}
          </div>
        )}
      </div>
      <div className="text-2xl font-semibold text-neutral-900 tracking-tight leading-none">{value}</div>
      {sub && <div className="text-[11px] text-neutral-400">{sub}</div>}
    </div>
  );
}

// ─── Navigation ───────────────────────────────────────────────────────────────
const NAV: { id: NavSection; label: string; icon: typeof LayoutDashboard; badge?: number }[] = [
  { id: "dashboard",   label: "Dashboard",        icon: LayoutDashboard },
  { id: "reviews",     label: "Reviews",           icon: Star,         badge: 12 },
  { id: "goals",       label: "Goals & OKRs",      icon: Target },
  { id: "career",      label: "Career Roadmap",    icon: Map },
  { id: "succession",  label: "Succession",         icon: GitBranch },
  { id: "feedback",    label: "360° Feedback",     icon: MessageSquare, badge: 5 },
  { id: "analytics",   label: "Analytics",          icon: BarChart3 },
  { id: "approvals",   label: "Approvals",          icon: CheckSquare,  badge: 8 },
];

function Sidebar({ active, onChange }: { active: NavSection; onChange: (s: NavSection) => void }) {
  return (
    <aside className="flex flex-col h-full w-[220px] flex-shrink-0" style={{ backgroundColor: "#0C0C14" }}>
      <div className="px-5 py-[18px] flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: PRIMARY }}>
          <Zap size={13} className="text-white" />
        </div>
        <div>
          <div className="text-white text-sm font-semibold leading-tight">Apex</div>
          <div className="text-[10px] leading-tight" style={{ color: "rgba(255,255,255,0.3)" }}>Performance AI</div>
        </div>
      </div>

      <div className="px-3 mb-3">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer" style={{ backgroundColor: "rgba(255,255,255,0.05)" }}>
          <Search size={12} style={{ color: "rgba(255,255,255,0.3)" }} />
          <span className="text-[12px]" style={{ color: "rgba(255,255,255,0.28)" }}>Search... ⌘K</span>
        </div>
      </div>

      <div className="px-3 mb-1">
        <span className="text-[9px] font-semibold uppercase tracking-[0.12em] px-2" style={{ color: "rgba(255,255,255,0.2)" }}>Workspace</span>
      </div>

      <nav className="flex-1 px-3 flex flex-col gap-0.5 overflow-y-auto">
        {NAV.map(item => {
          const active_ = active === item.id;
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              onClick={() => onChange(item.id)}
              className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left transition-all"
              style={{
                backgroundColor: active_ ? "rgba(255,255,255,0.09)" : "transparent",
                color: active_ ? "#fff" : "rgba(255,255,255,0.58)",
              }}
            >
              <Icon size={14} />
              <span className="text-[13px] flex-1 truncate" style={{ fontFamily: "Plus Jakarta Sans, sans-serif" }}>{item.label}</span>
              {item.badge != null && (
                <span
                  className="text-[10px] px-1.5 py-px rounded-full"
                  style={{
                    fontFamily: "DM Mono, monospace",
                    backgroundColor: active_ ? "rgba(255,255,255,0.14)" : "rgba(255,255,255,0.07)",
                    color: active_ ? "#fff" : "rgba(255,255,255,0.4)",
                  }}
                >{item.badge}</span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="px-3 py-4" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
        <div className="flex items-center gap-2.5 px-2">
          <Av name="Alex Morgan" size="sm" />
          <div className="flex-1 min-w-0">
            <div className="text-[12px] font-medium text-white truncate">Alex Morgan</div>
            <div className="text-[10px] truncate" style={{ color: "rgba(255,255,255,0.3)" }}>HRBP · Enterprise</div>
          </div>
          <Settings size={13} className="cursor-pointer opacity-30 hover:opacity-60 transition-opacity text-white" />
        </div>
      </div>
    </aside>
  );
}

// ─── Top Bar ─────────────────────────────────────────────────────────────────
const SECTION_LABELS: Record<NavSection, string> = {
  dashboard:  "Command Center",
  reviews:    "Performance Reviews",
  goals:      "Goals & OKRs",
  career:     "Career Roadmap",
  succession: "Succession Planning",
  feedback:   "360° Feedback",
  analytics:  "People Analytics",
  approvals:  "Approval Queue",
};

function TopBar({ section }: { section: NavSection }) {
  return (
    <header className="h-12 flex items-center justify-between px-6 bg-white border-b border-black/[0.06] flex-shrink-0">
      <div className="flex items-center gap-1.5 text-[12px]" style={{ color: "#71718A" }}>
        <span>Acme Corp</span>
        <ChevronRight size={11} />
        <span className="text-neutral-700 font-medium">{SECTION_LABELS[section]}</span>
      </div>
      <div className="flex items-center gap-2">
        <button className="relative p-1.5 rounded-lg hover:bg-neutral-100 transition-colors">
          <Bell size={15} className="text-neutral-400" />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full" style={{ backgroundColor: PRIMARY }} />
        </button>
        <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-black/[0.08] text-[12px] font-medium text-neutral-600 hover:bg-neutral-50 transition-colors">
          <Calendar size={12} />
          Q1 2025
          <ChevronDown size={11} className="text-neutral-400" />
        </button>
        <button
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-medium text-white hover:opacity-90 transition-opacity"
          style={{ backgroundColor: PRIMARY }}
        >
          <Plus size={13} />
          New
        </button>
      </div>
    </header>
  );
}

// ─── DASHBOARD ────────────────────────────────────────────────────────────────
const perfTrend = [
  { m: "Jul", score: 72, bench: 70 }, { m: "Aug", score: 73, bench: 70 },
  { m: "Sep", score: 75, bench: 71 }, { m: "Oct", score: 74, bench: 71 },
  { m: "Nov", score: 77, bench: 72 }, { m: "Dec", score: 76, bench: 72 },
  { m: "Jan", score: 78, bench: 72 },
];
const deptPerf = [
  { d: "Eng",    s: 82 }, { d: "Product", s: 78 }, { d: "Design", s: 85 },
  { d: "Sales",  s: 71 }, { d: "Mktg",    s: 75 }, { d: "Ops",    s: 69 },
];
const AI_SIGNALS = [
  { icon: AlertTriangle, color: AI_RED,   text: "7 employees show early attrition signals. Recommend 1:1s with managers.",              t: "2h ago"  },
  { icon: TrendingUp,    color: AI_GREEN, text: "Engineering team +8% this quarter — new onboarding cohort performing above baseline.", t: "4h ago"  },
  { icon: Zap,           color: AI_AMBER, text: "23 Q4 reviews awaiting calibration. Deadline in 6 days.",                             t: "5h ago"  },
  { icon: Sparkles,      color: PRIMARY,  text: "3 high-potential ICs not yet nominated for succession. Recommend review.",             t: "1d ago"  },
];

function DashboardView() {
  return (
    <div className="flex h-full overflow-hidden">
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        <div className="grid grid-cols-4 gap-3">
          <KPI label="Performance Index" value="78.4" sub="Team avg · all depts"    trend="+3.2 vs Q3" up />
          <KPI label="Reviews Pending"   value="23"   sub="12 need AI calibration"  trend="−5 this week" up />
          <KPI label="Goals On Track"    value="68%"  sub="Target: 72%"             trend="−4% vs target" up={false} />
          <KPI label="Attrition Risk"    value="7"    sub="2 critical, 5 elevated"  trend="+2 this week" up={false} />
        </div>

        <div className="bg-white rounded-xl border border-black/[0.06] p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-[13px] font-semibold text-neutral-900">Performance Trend</div>
              <div className="text-[11px] text-neutral-400">Team average vs industry benchmark · 7-month rolling</div>
            </div>
            <div className="flex items-center gap-4 text-[11px] text-neutral-400">
              <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-0.5 rounded-full" style={{ backgroundColor: PRIMARY }} />Team</span>
              <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-0.5 rounded-full bg-neutral-300" />Benchmark</span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={148}>
            <AreaChart data={perfTrend} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
              <defs>
                <linearGradient id="pg1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={PRIMARY} stopOpacity={0.14} />
                  <stop offset="95%" stopColor={PRIMARY} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#F0F0F6" vertical={false} />
              <XAxis dataKey="m"    tick={{ fontSize: 10, fill: "#B0B0C8" }} axisLine={false} tickLine={false} />
              <YAxis domain={[65, 85]} tick={{ fontSize: 10, fill: "#B0B0C8" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid rgba(0,0,0,0.08)", boxShadow: "0 4px 16px rgba(0,0,0,0.08)" }} />
              <Area type="monotone" dataKey="score" stroke={PRIMARY}      strokeWidth={2} fill="url(#pg1)" dot={false} name="Team" />
              <Line type="monotone" dataKey="bench" stroke="#D1D5DB"      strokeWidth={1.5} dot={false} strokeDasharray="4 4" name="Benchmark" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl border border-black/[0.06] p-4">
          <div className="text-[13px] font-semibold text-neutral-900 mb-0.5">Department Performance</div>
          <div className="text-[11px] text-neutral-400 mb-3">Composite score by department · current quarter</div>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={deptPerf} barSize={18} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F0F0F6" vertical={false} />
              <XAxis dataKey="d" tick={{ fontSize: 10, fill: "#B0B0C8" }} axisLine={false} tickLine={false} />
              <YAxis domain={[60, 90]} tick={{ fontSize: 10, fill: "#B0B0C8" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid rgba(0,0,0,0.08)" }} />
              <Bar dataKey="s" fill={PRIMARY} radius={[4, 4, 0, 0]} name="Score" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Right rail */}
      <div className="w-[272px] flex-shrink-0 bg-white border-l border-black/[0.06] overflow-y-auto">
        <div className="p-4 border-b border-black/[0.06]">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0" style={{ backgroundColor: PRIMARY }}>
              <Sparkles size={10} className="text-white" />
            </div>
            <span className="text-[12px] font-semibold text-neutral-700">AI Insights</span>
            <span className="ml-auto text-[9px] font-medium text-emerald-500 font-mono uppercase tracking-wider">● Live</span>
          </div>
          <div className="space-y-2">
            {AI_SIGNALS.map((sig, i) => {
              const Icon = sig.icon;
              return (
                <div key={i} className="flex gap-2.5 p-2.5 rounded-lg bg-neutral-50/80 hover:bg-neutral-100/70 cursor-pointer transition-colors">
                  <div className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0" style={{ backgroundColor: sig.color + "18" }}>
                    <Icon size={10} style={{ color: sig.color }} />
                  </div>
                  <div>
                    <p className="text-[11px] text-neutral-600 leading-snug">{sig.text}</p>
                    <p className="text-[10px] text-neutral-400 mt-0.5">{sig.t}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="p-4 border-b border-black/[0.06]">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[12px] font-semibold text-neutral-700">Top Performers</span>
            <span className="text-[11px] cursor-pointer" style={{ color: PRIMARY }}>View all</span>
          </div>
          {[
            { name: "Priya Sharma",  role: "Sr. Engineer",  s: 96, d: "+4" },
            { name: "James Liu",     role: "Staff Engineer", s: 94, d: "+7" },
            { name: "Sofia Mendez",  role: "Design Lead",    s: 92, d: "+2" },
          ].map((p, i) => (
            <div key={i} className="flex items-center gap-2.5 py-2">
              <span className="text-[10px] text-neutral-300 w-3 flex-shrink-0 font-mono">{i + 1}</span>
              <Av name={p.name} size="xs" />
              <div className="flex-1 min-w-0">
                <div className="text-[12px] font-medium text-neutral-800 truncate">{p.name}</div>
                <div className="text-[10px] text-neutral-400 truncate">{p.role}</div>
              </div>
              <div className="text-right">
                <div className="text-[12px] font-semibold text-neutral-800">{p.s}</div>
                <div className="text-[10px] text-emerald-600">{p.d}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[12px] font-semibold text-neutral-700">Attrition Risk</span>
            <AlertTriangle size={12} className="text-amber-500" />
          </div>
          {[
            { name: "David Park",   role: "Eng Manager",  risk: "Critical", signals: 4 },
            { name: "Aisha Hassan", role: "Sr. Analyst",  risk: "Elevated", signals: 3 },
            { name: "Tom Nguyen",   role: "Sales Lead",   risk: "Elevated", signals: 2 },
          ].map((p, i) => (
            <div key={i} className="flex items-center gap-2.5 py-2 rounded-lg px-1 hover:bg-neutral-50 cursor-pointer transition-colors">
              <Av name={p.name} size="xs" />
              <div className="flex-1 min-w-0">
                <div className="text-[12px] font-medium text-neutral-800 truncate">{p.name}</div>
                <div className="text-[10px] text-neutral-400">{p.role} · {p.signals} signals</div>
              </div>
              <Chip status={p.risk} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── REVIEWS ──────────────────────────────────────────────────────────────────
const REVIEWS = [
  { name: "Priya Sharma",   role: "Sr. Engineer",   dept: "Engineering", self: 4.7, mgr: 4.8, ai: 4.6, conf: 93, status: "Approved"      },
  { name: "Marcus Williams",role: "Product Manager", dept: "Product",     self: 3.9, mgr: 4.2, ai: 4.0, conf: 87, status: "Pending Review" },
  { name: "Sarah Chen",     role: "UX Designer",     dept: "Design",      self: 4.5, mgr: 4.4, ai: 4.5, conf: 91, status: "Approved"      },
  { name: "James Liu",      role: "Staff Engineer",  dept: "Engineering", self: 4.2, mgr: 4.6, ai: 4.3, conf: 89, status: "Calibrating"   },
  { name: "Aisha Hassan",   role: "Sr. Analyst",     dept: "Operations",  self: 3.5, mgr: 3.8, ai: 3.7, conf: 78, status: "Pending Review" },
  { name: "Daniel Reyes",   role: "Sales Director",  dept: "Sales",       self: 4.0, mgr: 3.7, ai: 3.9, conf: 72, status: "AI Draft"      },
  { name: "Emily Park",     role: "Marketing Lead",  dept: "Marketing",   self: 4.3, mgr: 4.1, ai: 4.2, conf: 85, status: "Approved"      },
  { name: "Kevin O'Brien",  role: "Eng Manager",     dept: "Engineering", self: 4.6, mgr: 4.5, ai: 4.4, conf: 90, status: "Calibrating"   },
];

function ReviewsView() {
  const [sel, setSel] = useState(0);
  const r = REVIEWS[sel];
  return (
    <div className="flex h-full overflow-hidden">
      <div className="flex-1 overflow-y-auto">
        <div className="px-5 py-3 bg-white border-b border-black/[0.06] flex items-center gap-2.5 sticky top-0 z-10">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-black/[0.07] text-[12px] text-neutral-400 flex-1 max-w-xs cursor-text">
            <Search size={12} />Search reviews...
          </div>
          <button className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-black/[0.07] text-[12px] text-neutral-500 hover:bg-neutral-50 transition-colors">
            <Filter size={11} />Filter
          </button>
          <div className="flex gap-0.5 ml-1">
            {["All","Pending","AI Draft","Approved"].map((f, fi) => (
              <button key={f} className={`px-3 py-1.5 rounded-lg text-[11px] font-medium transition-colors ${fi === 0 ? "bg-neutral-900 text-white" : "text-neutral-500 hover:bg-neutral-100"}`}>{f}</button>
            ))}
          </div>
        </div>

        <table className="w-full text-sm min-w-[700px]">
          <thead className="bg-neutral-50 sticky top-[48px] z-10">
            <tr className="border-b border-black/[0.05]">
              {["Employee","Period","Self","Mgr","AI Score","Confidence","Status",""].map((h, i) => (
                <th key={i} className={`px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-neutral-400 ${i > 1 && i < 5 ? "text-center" : "text-left"}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-black/[0.035]">
            {REVIEWS.map((rev, i) => (
              <tr key={i} onClick={() => setSel(i)} className={`cursor-pointer transition-colors ${sel === i ? "bg-violet-50/60" : "hover:bg-neutral-50/70"}`}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <Av name={rev.name} size="sm" />
                    <div>
                      <div className="text-[13px] font-medium text-neutral-800">{rev.name}</div>
                      <div className="text-[11px] text-neutral-400">{rev.role} · {rev.dept}</div>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 text-[11px] text-neutral-400" style={{ fontFamily: "DM Mono,monospace" }}>Q4 2024</td>
                <td className="px-4 py-3 text-center text-[13px] font-semibold text-neutral-600">{rev.self.toFixed(1)}</td>
                <td className="px-4 py-3 text-center text-[13px] font-semibold text-neutral-600">{rev.mgr.toFixed(1)}</td>
                <td className="px-4 py-3 text-center text-[13px] font-semibold" style={{ color: PRIMARY }}>{rev.ai.toFixed(1)}</td>
                <td className="px-4 py-3"><AIBadge score={rev.conf} /></td>
                <td className="px-4 py-3"><Chip status={rev.status} /></td>
                <td className="px-4 py-3">
                  <button className="p-1 rounded hover:bg-neutral-100 transition-colors"><MoreHorizontal size={13} className="text-neutral-300" /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Detail panel */}
      <div className="w-[300px] flex-shrink-0 border-l border-black/[0.06] bg-white overflow-y-auto">
        <div className="p-4 border-b border-black/[0.06]">
          <div className="flex items-center gap-3 mb-3">
            <Av name={r.name} size="md" />
            <div>
              <div className="text-[13px] font-semibold text-neutral-900">{r.name}</div>
              <div className="text-[11px] text-neutral-400">{r.role} · {r.dept}</div>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {[["Self", r.self.toFixed(1), false],["Mgr", r.mgr.toFixed(1), false],["AI", r.ai.toFixed(1), true]].map(([lbl, val, accent]) => (
              <div key={String(lbl)} className="bg-neutral-50 rounded-lg p-2.5 text-center">
                <div className={`text-[18px] font-semibold ${accent ? "text-violet-600" : "text-neutral-700"}`}>{val}</div>
                <div className="text-[10px] text-neutral-400 mt-0.5">{lbl}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="p-4 border-b border-black/[0.06]">
          <div className="flex items-center gap-2 mb-2.5">
            <Bot size={12} style={{ color: PRIMARY }} />
            <span className="text-[11px] font-semibold text-neutral-700">AI Assessment</span>
          </div>
          <AIBadge score={r.conf} />
          <p className="text-[11px] text-neutral-500 mt-2.5 leading-relaxed">
            Strong delivery consistency with positive peer sentiment across 6 reviewers. Score alignment with manager rating indicates reliable calibration. Minor self-assessment variance of {Math.abs(r.mgr - r.self).toFixed(1)}.
          </p>
          {r.conf < 85 && (
            <div className="mt-2.5 p-2.5 rounded-lg border border-amber-200 bg-amber-50">
              <p className="text-[10px] text-amber-700 leading-snug">⚠ Human calibration recommended — confidence below threshold.</p>
            </div>
          )}
        </div>

        <div className="p-4">
          <div className="text-[11px] font-semibold text-neutral-600 mb-2.5">Human-in-the-Loop Actions</div>
          <div className="space-y-2">
            <button className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-[12px] font-medium text-white hover:opacity-90 transition-opacity" style={{ backgroundColor: PRIMARY }}>
              <UserCheck size={13} />Approve Review
            </button>
            <button className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-[12px] font-medium text-neutral-700 border border-black/[0.08] hover:bg-neutral-50 transition-colors">
              <Activity size={13} />Request Calibration
            </button>
            <button className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-[12px] font-medium text-neutral-400 hover:bg-neutral-50 transition-colors">
              <X size={13} />Override AI Score
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── GOALS ────────────────────────────────────────────────────────────────────
type Goal = { level: string; title: string; owner: string; progress: number; status: string; children?: Goal[] };

const GOALS: Goal[] = [{
  level: "Company", title: "Achieve $50M ARR by end of year", owner: "Leadership", progress: 68, status: "On Track",
  children: [
    {
      level: "Department", title: "Grow enterprise pipeline 40% in H1", owner: "Sales", progress: 72, status: "On Track",
      children: [
        { level: "Individual", title: "Close 5 enterprise deals this quarter", owner: "Daniel Reyes", progress: 60, status: "At Risk" },
        { level: "Individual", title: "Qualify 20 inbound enterprise leads", owner: "Aisha Hassan", progress: 80, status: "On Track" },
      ],
    },
    {
      level: "Department", title: "Ship 3 AI-powered product features", owner: "Product", progress: 45, status: "At Risk",
      children: [
        { level: "Individual", title: "Deliver AI coaching module v1", owner: "Marcus Williams", progress: 35, status: "Behind" },
        { level: "Individual", title: "Redesign employee onboarding flow", owner: "Sarah Chen", progress: 90, status: "On Track" },
      ],
    },
  ],
}];

const LEVEL_COLOR: Record<string, string> = { Company: "#5B5BD6", Department: "#00B87C", Individual: "#F59E0B" };

function GoalRow({ goal, depth = 0 }: { goal: Goal; depth?: number }) {
  const [open, setOpen] = useState(depth < 1);
  const has = (goal.children?.length ?? 0) > 0;
  const c = LEVEL_COLOR[goal.level] ?? "#9CA3AF";
  const pct = goal.progress;
  const barColor = pct >= 70 ? AI_GREEN : pct >= 40 ? AI_AMBER : AI_RED;
  return (
    <div>
      <div
        className="flex items-center px-5 py-2.5 border-b border-black/[0.035] hover:bg-neutral-50/70 cursor-pointer transition-colors"
        style={{ paddingLeft: `${20 + depth * 28}px` }}
        onClick={() => has && setOpen(!open)}
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {has
            ? <ChevronRight size={12} className={`text-neutral-300 flex-shrink-0 transition-transform ${open ? "rotate-90" : ""}`} />
            : <span className="w-3 flex-shrink-0" />}
          <span className="text-[9px] font-semibold uppercase tracking-widest px-1.5 py-0.5 rounded flex-shrink-0" style={{ backgroundColor: c + "18", color: c }}>{goal.level.slice(0,4)}</span>
          <span className="text-[13px] text-neutral-800 truncate">{goal.title}</span>
        </div>
        <div className="flex items-center gap-5 flex-shrink-0 ml-4">
          <div className="flex items-center gap-1.5">
            <Av name={goal.owner} size="xs" />
            <span className="text-[11px] text-neutral-500 w-24 truncate">{goal.owner}</span>
          </div>
          <div className="flex items-center gap-2 w-28">
            <div className="flex-1 h-1 bg-neutral-100 rounded-full overflow-hidden">
              <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: barColor }} />
            </div>
            <span className="text-[10px] w-7 text-right text-neutral-500" style={{ fontFamily: "DM Mono,monospace" }}>{pct}%</span>
          </div>
          <Chip status={goal.status} />
        </div>
      </div>
      {open && goal.children?.map((ch, i) => <GoalRow key={i} goal={ch} depth={depth + 1} />)}
    </div>
  );
}

function GoalsView() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="px-5 py-3 bg-white border-b border-black/[0.06] flex items-center gap-2 sticky top-0 z-10">
        <div className="flex gap-0.5">
          {["All Goals","Company","Department","Individual"].map((f, fi) => (
            <button key={f} className={`px-3 py-1.5 rounded-lg text-[11px] font-medium transition-colors ${fi === 0 ? "bg-neutral-900 text-white" : "text-neutral-500 hover:bg-neutral-100"}`}>{f}</button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-black/[0.07] text-[11px] text-neutral-500 hover:bg-neutral-50 transition-colors"><Filter size={11} />Filter</button>
          <button className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[11px] font-medium text-white hover:opacity-90 transition-opacity" style={{ backgroundColor: PRIMARY }}><Plus size={11} />Add Goal</button>
        </div>
      </div>
      <div className="bg-neutral-50 px-5 py-2 border-b border-black/[0.05] flex items-center">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-neutral-400 flex-1">Goal</span>
        <div className="flex items-center gap-5 flex-shrink-0">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-neutral-400 w-32">Owner</span>
          <span className="text-[10px] font-semibold uppercase tracking-widest text-neutral-400 w-28">Progress</span>
          <span className="text-[10px] font-semibold uppercase tracking-widest text-neutral-400">Status</span>
        </div>
      </div>
      <div className="bg-white">
        {GOALS.map((g, i) => <GoalRow key={i} goal={g} />)}
      </div>
      <div className="m-5 bg-white rounded-xl border border-black/[0.06] p-4">
        <div className="grid grid-cols-4 divide-x divide-black/[0.05]">
          {[["Total Goals","24","#5B5BD6"],["On Track","16 (67%)","#00B87C"],["At Risk","6 (25%)","#F59E0B"],["Behind","2 (8%)","#EF4444"]].map(([l, v, c]) => (
            <div key={String(l)} className="text-center px-4">
              <div className="text-[20px] font-semibold" style={{ color: c }}>{v}</div>
              <div className="text-[11px] text-neutral-400 mt-0.5">{l}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── CAREER ROADMAP ───────────────────────────────────────────────────────────
const skillsRadar = [
  { s: "Leadership", v: 82 }, { s: "Technical", v: 91 }, { s: "Communication", v: 75 },
  { s: "Strategy", v: 68 },   { s: "Execution", v: 88 }, { s: "Mentoring", v: 72 },
];
const milestones = [
  { date: "Q2 2024", title: "Promoted to Sr. Engineer", done: true, current: false },
  { date: "Q3 2024", title: "Led platform migration (45 services)", done: true, current: false },
  { date: "Q4 2024", title: "Completed Leadership Fundamentals course", done: true, current: false },
  { date: "Q1 2025", title: "Shadow Eng Manager in sprint ceremonies", done: false, current: true },
  { date: "Q2 2025", title: "Own team OKR planning cycle", done: false, current: false },
  { date: "Q3 2025", title: "Ready for Engineering Manager consideration", done: false, current: false },
];

function CareerRoadmapView() {
  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="grid grid-cols-[1fr_260px] gap-4">
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-black/[0.06] p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Av name="Priya Sharma" size="md" />
                <div>
                  <div className="text-[14px] font-semibold text-neutral-900">Priya Sharma</div>
                  <div className="text-[11px] text-neutral-400">Sr. Software Engineer · L5 · Engineering</div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-[10px] text-neutral-400 mb-0.5">AI Career Score</div>
                <div className="text-[22px] font-semibold" style={{ color: PRIMARY }}>87</div>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {[
                { label: "Current Role",  val: "Sr. Engineer (L5)",  icon: Briefcase, color: PRIMARY  },
                { label: "Target Role",   val: "Eng Manager (L6)",   icon: Award,     color: AI_GREEN },
                { label: "Est. Readiness",val: "~9 months",          icon: Clock,     color: AI_AMBER },
              ].map(c => {
                const Icon = c.icon;
                return (
                  <div key={c.label} className="flex items-center gap-2.5 p-3 rounded-lg" style={{ backgroundColor: c.color + "10" }}>
                    <Icon size={14} style={{ color: c.color }} />
                    <div>
                      <div className="text-[9px] uppercase tracking-widest font-semibold text-neutral-400">{c.label}</div>
                      <div className="text-[12px] font-semibold text-neutral-800 mt-0.5">{c.val}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-black/[0.06] p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="text-[13px] font-semibold text-neutral-900">Skills Assessment</div>
                <div className="text-[11px] text-neutral-400">AI-derived from reviews, feedback, and project data</div>
              </div>
              <AIBadge score={88} />
            </div>
            <div className="flex gap-4 items-start">
              <ResponsiveContainer width="60%" height={200}>
                <RadarChart data={skillsRadar.map(s => ({ subject: s.s, A: s.v, fullMark: 100 }))}>
                  <PolarGrid stroke="#F0F0F6" />
                  <PolarAngleAxis dataKey="subject" tick={{ fontSize: 10, fill: "#B0B0C8" }} />
                  <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} axisLine={false} />
                  <Radar name="Skills" dataKey="A" stroke={PRIMARY} fill={PRIMARY} fillOpacity={0.13} strokeWidth={2} />
                </RadarChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-2 pt-4">
                {skillsRadar.map(s => {
                  const bc = s.v >= 80 ? PRIMARY : s.v >= 65 ? AI_AMBER : AI_RED;
                  return (
                    <div key={s.s} className="flex items-center gap-2">
                      <span className="text-[11px] text-neutral-500 w-24 truncate">{s.s}</span>
                      <div className="flex-1 h-1 bg-neutral-100 rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${s.v}%`, backgroundColor: bc }} />
                      </div>
                      <span className="text-[10px] text-neutral-400 w-6 text-right" style={{ fontFamily: "DM Mono,monospace" }}>{s.v}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-black/[0.06] p-4">
            <div className="text-[13px] font-semibold text-neutral-900 mb-3">Development Milestones</div>
            <div>
              {milestones.map((m, i) => (
                <div key={i} className="flex gap-3 pb-3">
                  <div className="flex flex-col items-center">
                    <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${m.done ? "bg-emerald-500" : m.current ? "bg-white ring-2 ring-violet-500" : "bg-neutral-100"}`}>
                      {m.done ? <Check size={10} className="text-white" />
                        : m.current ? <div className="w-2 h-2 rounded-full" style={{ backgroundColor: PRIMARY }} />
                        : <div className="w-1.5 h-1.5 rounded-full bg-neutral-300" />}
                    </div>
                    {i < milestones.length - 1 && (
                      <div className={`w-px flex-1 mt-1 ${m.done ? "bg-emerald-200" : "bg-neutral-100"}`} style={{ minHeight: 12 }} />
                    )}
                  </div>
                  <div className="pt-0.5">
                    <div className="text-[9px] font-mono text-neutral-400">{m.date}</div>
                    <div className={`text-[11px] mt-0.5 leading-snug ${m.current ? "font-semibold text-violet-700" : m.done ? "text-neutral-500" : "text-neutral-600"}`}>{m.title}</div>
                    {m.current && <span className="text-[10px] text-violet-400">Currently in progress</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-black/[0.06] p-4">
            <div className="flex items-center gap-1.5 mb-2.5">
              <Sparkles size={12} style={{ color: PRIMARY }} />
              <span className="text-[12px] font-semibold text-neutral-700">AI Recommendations</span>
            </div>
            <div className="space-y-2">
              {["Increase leadership visibility during Q1 planning cycle","Enroll in Systems Design course (linked in Learning Hub)","Pair with EM Kevin on weekly sprint retrospectives"].map((rec, i) => (
                <div key={i} className="flex gap-2 text-[11px] text-neutral-500 leading-snug">
                  <span className="flex-shrink-0 font-semibold" style={{ color: PRIMARY }}>→</span>
                  {rec}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── SUCCESSION ───────────────────────────────────────────────────────────────
const TALENT = [
  { name: "Priya Sharma",  perf: "High",   pot: "High",   role: "Sr. Engineer",  ready: "Ready 1-2yr", risk: "Low"    },
  { name: "James Liu",     perf: "High",   pot: "High",   role: "Staff Engineer",ready: "Ready Now",   risk: "Low"    },
  { name: "Kevin O'Brien", perf: "High",   pot: "Medium", role: "Eng Manager",   ready: "Ready Now",   risk: "Medium" },
  { name: "Marcus Williams",perf:"Medium", pot: "High",   role: "Product Lead",  ready: "Ready 1-2yr", risk: "Low"    },
  { name: "Emily Park",    perf: "Medium", pot: "Medium", role: "Mktg Lead",     ready: "Ready 1-2yr", risk: "Medium" },
  { name: "Daniel Reyes",  perf: "Low",    pot: "Medium", role: "Sales Director",ready: "Nominated",   risk: "High"   },
  { name: "Sarah Chen",    perf: "High",   pot: "Medium", role: "Design Lead",   ready: "Ready Now",   risk: "Low"    },
  { name: "Aisha Hassan",  perf: "Medium", pot: "Low",    role: "Sr. Analyst",   ready: "Nominated",   risk: "High"   },
  { name: "Tom Nguyen",    perf: "Low",    pot: "Low",    role: "Sales Rep",     ready: "Nominated",   risk: "Critical"},
];

const NINE_BOX = [
  { perf:"High",   pot:"High",   label:"Stars",         color:"#5B5BD6" },
  { perf:"Medium", pot:"High",   label:"High Potential",color:"#8B5CF6" },
  { perf:"Low",    pot:"High",   label:"Dilemma",       color:"#F59E0B" },
  { perf:"High",   pot:"Medium", label:"Core Leaders",  color:"#00B87C" },
  { perf:"Medium", pot:"Medium", label:"Core Employee", color:"#6B7280" },
  { perf:"Low",    pot:"Medium", label:"Under Performer",color:"#EF4444"},
  { perf:"High",   pot:"Low",    label:"Highly Valued", color:"#06B6D4" },
  { perf:"Medium", pot:"Low",    label:"Solid Performer",color:"#9CA3AF"},
  { perf:"Low",    pot:"Low",    label:"Disengaged",    color:"#DC2626" },
];

function SuccessionView() {
  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="grid grid-cols-[1fr_260px] gap-4">
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-black/[0.06] p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="text-[13px] font-semibold text-neutral-900">9-Box Performance × Potential</div>
                <div className="text-[11px] text-neutral-400">AI-calibrated placement · Q4 2024</div>
              </div>
              <AIBadge score={85} />
            </div>
            <div className="flex gap-3">
              <div className="flex flex-col justify-center gap-1 text-[9px] text-neutral-400" style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>
                <span>HIGH POTENTIAL</span>
              </div>
              <div className="flex-1">
                <div className="grid grid-cols-3 gap-1.5 mb-1" style={{ gridTemplateRows: "repeat(3,88px)" }}>
                  {NINE_BOX.map((box, bi) => {
                    const members = TALENT.filter(t => t.perf === box.perf && t.pot === box.pot);
                    return (
                      <div key={bi} className="rounded-lg p-2 flex flex-col" style={{ backgroundColor: box.color + "12", border: `1px solid ${box.color}25` }}>
                        <div className="text-[9px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: box.color }}>{box.label}</div>
                        <div className="flex flex-wrap gap-1">
                          {members.map((m, mi) => (
                            <div key={mi} title={m.name}><Av name={m.name} size="xs" /></div>
                          ))}
                          {members.length === 0 && <div className="text-[9px] text-neutral-300">—</div>}
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="flex justify-between text-[9px] text-neutral-400 px-1">
                  <span>LOW PERFORMANCE</span>
                  <span>HIGH PERFORMANCE</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-black/[0.06] p-4">
            <div className="text-[13px] font-semibold text-neutral-900 mb-3">Key Role Pipeline</div>
            <div className="space-y-2.5">
              {[
                { role: "VP Engineering",     incumbent: "Chris Park",   depth: 2, risk: "Medium"   },
                { role: "Head of Product",    incumbent: "Lisa Chen",    depth: 1, risk: "Critical"  },
                { role: "Sr. Dir. Sales",     incumbent: "Robert Kim",   depth: 3, risk: "Low"       },
                { role: "Head of Design",     incumbent: "Maria Santos", depth: 2, risk: "Low"       },
              ].map((p, i) => (
                <div key={i} className="p-3 rounded-lg border border-black/[0.06] hover:border-black/10 cursor-pointer transition-colors">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-[12px] font-semibold text-neutral-800">{p.role}</span>
                    <Chip status={p.risk} />
                  </div>
                  <div className="text-[10px] text-neutral-400 mb-2">Incumbent: {p.incumbent}</div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-neutral-400">Depth:</span>
                    <div className="flex gap-0.5">
                      {[0,1,2,3].map(d => (
                        <div key={d} className="w-5 h-1 rounded-full" style={{ backgroundColor: d < p.depth ? PRIMARY : "#E5E5EE" }} />
                      ))}
                    </div>
                    <span className="text-[10px] text-neutral-400" style={{ fontFamily: "DM Mono,monospace" }}>{p.depth}/4</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-black/[0.06] p-4">
            <div className="text-[12px] font-semibold text-neutral-900 mb-3">Ready Talent Pool</div>
            <div className="space-y-2">
              {TALENT.filter(t => t.ready !== "Nominated").map((t, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Av name={t.name} size="xs" />
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] font-medium text-neutral-800 truncate">{t.name}</div>
                    <div className="text-[10px] text-neutral-400 truncate">{t.role}</div>
                  </div>
                  <Chip status={t.ready} />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── 360 FEEDBACK ─────────────────────────────────────────────────────────────
const FEEDBACK_DATA = [
  { name: "Priya Sharma",   req: 8, rec: 7, themes: ["Technical Excellence","Collaborative","Mentoring"],     sentiment: 92, status: "Complete"    },
  { name: "Marcus Williams",req: 6, rec: 4, themes: ["Strategic Thinking","Communication"],                   sentiment: 78, status: "In Progress" },
  { name: "James Liu",      req: 7, rec: 7, themes: ["Leadership","Technical Depth","Reliability"],           sentiment: 89, status: "Complete"    },
  { name: "Daniel Reyes",   req: 5, rec: 2, themes: ["Client Focus"],                                        sentiment: 65, status: "Overdue"     },
  { name: "Sarah Chen",     req: 6, rec: 5, themes: ["Design Quality","Process","Collaboration"],             sentiment: 88, status: "In Progress" },
];

function FeedbackView() {
  const [sel, setSel] = useState(0);
  const f = FEEDBACK_DATA[sel];
  return (
    <div className="flex h-full overflow-hidden">
      <div className="flex-1 overflow-y-auto">
        <div className="px-5 py-3 bg-white border-b border-black/[0.06] flex items-center gap-3 sticky top-0 z-10">
          <span className="text-[13px] font-medium text-neutral-700">Q4 2024 · 360° Review Cycle</span>
          <Chip status="In Progress" />
          <div className="ml-auto text-[11px] text-neutral-400">Cycle closes Dec 31, 2024 · {FEEDBACK_DATA.filter(f => f.status === "Complete").length}/{FEEDBACK_DATA.length} complete</div>
        </div>
        <table className="w-full bg-white min-w-[640px]">
          <thead className="bg-neutral-50 sticky top-[48px] z-10">
            <tr className="border-b border-black/[0.05]">
              {["Employee","Req","Rec","AI Themes","Sentiment","Status"].map((h, i) => (
                <th key={i} className={`px-4 py-2.5 text-[10px] font-semibold uppercase tracking-widest text-neutral-400 ${i === 0 ? "text-left" : i > 0 && i < 3 ? "text-center" : "text-left"}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-black/[0.035]">
            {FEEDBACK_DATA.map((fd, i) => (
              <tr key={i} onClick={() => setSel(i)} className={`cursor-pointer transition-colors ${sel === i ? "bg-violet-50/60" : "hover:bg-neutral-50/70"}`}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <Av name={fd.name} size="sm" />
                    <span className="text-[13px] font-medium text-neutral-800">{fd.name}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-center text-[12px] font-mono text-neutral-500">{fd.req}</td>
                <td className="px-4 py-3 text-center">
                  <span className={`text-[12px] font-semibold font-mono ${fd.rec === fd.req ? "text-emerald-600" : "text-amber-600"}`}>{fd.rec}</span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {fd.themes.map(t => (
                      <span key={t} className="text-[10px] px-2 py-px rounded-full bg-violet-50 text-violet-700 border border-violet-100">{t}</span>
                    ))}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className="w-14 h-1 bg-neutral-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${fd.sentiment}%`, backgroundColor: fd.sentiment >= 85 ? AI_GREEN : fd.sentiment >= 70 ? AI_AMBER : AI_RED }} />
                    </div>
                    <span className="text-[10px] text-neutral-500" style={{ fontFamily: "DM Mono,monospace" }}>{fd.sentiment}%</span>
                  </div>
                </td>
                <td className="px-4 py-3"><Chip status={fd.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="w-[280px] flex-shrink-0 border-l border-black/[0.06] bg-white overflow-y-auto">
        <div className="p-4 border-b border-black/[0.06]">
          <div className="flex items-center gap-2.5 mb-3">
            <Av name={f.name} size="md" />
            <div>
              <div className="text-[13px] font-semibold text-neutral-900">{f.name}</div>
              <div className="text-[11px] text-neutral-400">Q4 2024 · 360° Review</div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-neutral-50 rounded-lg p-3 text-center">
              <div className="text-[18px] font-semibold text-neutral-800">{f.rec}/{f.req}</div>
              <div className="text-[10px] text-neutral-400 mt-0.5">Responses</div>
            </div>
            <div className="bg-neutral-50 rounded-lg p-3 text-center">
              <div className="text-[18px] font-semibold" style={{ color: f.sentiment >= 85 ? AI_GREEN : f.sentiment >= 70 ? AI_AMBER : AI_RED }}>{f.sentiment}%</div>
              <div className="text-[10px] text-neutral-400 mt-0.5">Sentiment</div>
            </div>
          </div>
        </div>

        <div className="p-4 border-b border-black/[0.06]">
          <div className="flex items-center gap-1.5 mb-2.5">
            <Bot size={11} style={{ color: PRIMARY }} />
            <span className="text-[11px] font-semibold text-neutral-700">AI Theme Analysis</span>
          </div>
          <div className="space-y-2">
            {f.themes.map((t, i) => {
              const colors = [PRIMARY, AI_GREEN, AI_AMBER];
              const c = colors[i % 3];
              return (
                <div key={i} className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: c }} />
                  <span className="text-[11px] text-neutral-600 flex-1">{t}</span>
                  <div className="w-14 h-1 bg-neutral-100 rounded-full overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${85 - i * 10}%`, backgroundColor: c }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="p-4">
          <div className="text-[11px] font-semibold text-neutral-600 mb-2.5">Actions</div>
          <div className="space-y-2">
            <button className="w-full py-2 rounded-lg text-[12px] font-medium text-white hover:opacity-90 transition-opacity" style={{ backgroundColor: PRIMARY }}>View Full Report</button>
            <button className="w-full py-2 rounded-lg text-[12px] font-medium text-neutral-700 border border-black/[0.08] hover:bg-neutral-50 transition-colors">Send Reminder</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── ANALYTICS ────────────────────────────────────────────────────────────────
const qPerf = [
  { q:"Q1 '24",avg:73,top:91,bot:52 }, { q:"Q2 '24",avg:74,top:93,bot:54 },
  { q:"Q3 '24",avg:75,top:92,bot:55 }, { q:"Q4 '24",avg:78,top:95,bot:57 },
];
const retention = [
  { m:"Jul",r:98.2 },{ m:"Aug",r:97.8 },{ m:"Sep",r:97.5 },
  { m:"Oct",r:96.9 },{ m:"Nov",r:97.2 },{ m:"Dec",r:96.8 },{ m:"Jan",r:97.1 },
];

const HEAT_ROWS = [
  { metric:"eNPS Score",           vals:[78,72,85,61,70,65] },
  { metric:"Goal Completion %",    vals:[82,75,88,64,73,68] },
  { metric:"Review Score",         vals:[82,78,85,71,75,69] },
  { metric:"Retention Rate %",     vals:[98,97,99,94,96,95] },
];
const HEAT_COLS = ["Eng","Product","Design","Sales","Mktg","Ops"];

function AnalyticsView() {
  return (
    <div className="h-full overflow-y-auto p-5 space-y-4">
      <div className="grid grid-cols-4 gap-3">
        <KPI label="Avg Performance Score" value="78.4" sub="vs 75.2 industry avg" trend="+3.2 QoQ" up />
        <KPI label="eNPS Score"            value="42"   sub="Industry avg: 31"     trend="+8 vs Q3" up />
        <KPI label="Review Completion"     value="91%"  sub="23 pending"           trend="+6% vs Q3" up />
        <KPI label="Retention Rate"        value="97.1%" sub="3 departures YTD"    trend="+0.3% MoM" up />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-black/[0.06] p-4">
          <div className="text-[13px] font-semibold text-neutral-900 mb-0.5">Performance Distribution</div>
          <div className="text-[11px] text-neutral-400 mb-3">Top / avg / bottom quartile by quarter</div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={qPerf} barSize={14} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F0F0F6" vertical={false} />
              <XAxis dataKey="q" tick={{ fontSize: 10, fill: "#B0B0C8" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#B0B0C8" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid rgba(0,0,0,0.08)" }} />
              <Bar dataKey="top" fill={PRIMARY}    radius={[3,3,0,0]} name="Top Quartile" />
              <Bar dataKey="avg" fill={AI_GREEN}   radius={[3,3,0,0]} name="Average" />
              <Bar dataKey="bot" fill="#E2E8F0"    radius={[3,3,0,0]} name="Bottom Quartile" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-xl border border-black/[0.06] p-4">
          <div className="text-[13px] font-semibold text-neutral-900 mb-0.5">Retention Trend</div>
          <div className="text-[11px] text-neutral-400 mb-3">Monthly retention rate (%) · 7-month rolling</div>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={retention} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
              <defs>
                <linearGradient id="rg1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={AI_GREEN} stopOpacity={0.14} />
                  <stop offset="95%" stopColor={AI_GREEN} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#F0F0F6" vertical={false} />
              <XAxis dataKey="m" tick={{ fontSize: 10, fill: "#B0B0C8" }} axisLine={false} tickLine={false} />
              <YAxis domain={[95, 100]} tick={{ fontSize: 10, fill: "#B0B0C8" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid rgba(0,0,0,0.08)" }} />
              <Area type="monotone" dataKey="r" stroke={AI_GREEN} strokeWidth={2} fill="url(#rg1)" dot={false} name="Retention %" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Correlation heatmap */}
      <div className="bg-white rounded-xl border border-black/[0.06] p-4">
        <div className="text-[13px] font-semibold text-neutral-900 mb-3">Engagement × Performance Heatmap</div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="text-left pb-2 text-[10px] font-semibold text-neutral-400 uppercase tracking-widest w-36">Metric</th>
                {HEAT_COLS.map(col => (
                  <th key={col} className="pb-2 text-[10px] font-semibold text-neutral-500 text-center">{col}</th>
                ))}
              </tr>
            </thead>
            <tbody className="space-y-1">
              {HEAT_ROWS.map(row => (
                <tr key={row.metric}>
                  <td className="py-1 pr-4 text-[11px] text-neutral-500 whitespace-nowrap">{row.metric}</td>
                  {row.vals.map((v, ci) => {
                    const intensity = (v - 60) / 40;
                    return (
                      <td key={ci} className="py-1 px-1">
                        <div
                          className="rounded text-center text-[10px] font-semibold py-1.5 mx-0.5"
                          style={{
                            fontFamily: "DM Mono,monospace",
                            backgroundColor: `rgba(91,91,214,${intensity * 0.22})`,
                            color: intensity > 0.55 ? PRIMARY : "#ABABC8",
                          }}
                        >{v}</div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── APPROVALS ────────────────────────────────────────────────────────────────
const APPROVALS = [
  { id:"APR-2401", type:"Review Sign-off",   employee:"Priya Sharma",    mgr:"Kevin O'Brien", deadline:"Jan 15", sla:"2d left",  priority:"High",     status:"Pending Review" },
  { id:"APR-2402", type:"Goal Override",      employee:"Daniel Reyes",    mgr:"Lisa Chen",     deadline:"Jan 12", sla:"Overdue",  priority:"Critical",  status:"Overdue"       },
  { id:"APR-2403", type:"Promotion Rec.",     employee:"James Liu",       mgr:"Kevin O'Brien", deadline:"Jan 20", sla:"7d left",  priority:"High",     status:"AI Draft"       },
  { id:"APR-2404", type:"Review Sign-off",   employee:"Marcus Williams", mgr:"Lisa Chen",     deadline:"Jan 18", sla:"5d left",  priority:"Medium",   status:"Pending Review" },
  { id:"APR-2405", type:"PIP Initiation",    employee:"Tom Nguyen",      mgr:"Robert Kim",    deadline:"Jan 10", sla:"Overdue",  priority:"Critical",  status:"Overdue"       },
  { id:"APR-2406", type:"Succession Nom.",   employee:"Sarah Chen",      mgr:"Maria Santos",  deadline:"Jan 22", sla:"9d left",  priority:"Medium",   status:"AI Draft"       },
  { id:"APR-2407", type:"Review Sign-off",   employee:"Emily Park",      mgr:"Chris Park",    deadline:"Jan 25", sla:"12d left", priority:"Low",      status:"Pending Review" },
  { id:"APR-2408", type:"Goal Override",      employee:"Aisha Hassan",    mgr:"Robert Kim",    deadline:"Jan 14", sla:"1d left",  priority:"High",     status:"Pending Review" },
];

function ApprovalsView() {
  const [approved, setApproved] = useState<string[]>([]);
  const [rejected, setRejected] = useState<string[]>([]);
  const approve = (id: string) => setApproved(p => [...p, id]);
  const reject  = (id: string) => setRejected(p => [...p, id]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-5 py-3 bg-white border-b border-black/[0.06] flex items-center gap-6 sticky top-0 z-10">
        {[
          { l:"Pending",         v: APPROVALS.length - approved.length - rejected.length, c: AI_AMBER },
          { l:"Overdue",         v: APPROVALS.filter(a=>a.sla==="Overdue").length,         c: AI_RED   },
          { l:"Approved Today",  v: approved.length,                                       c: AI_GREEN },
        ].map(m => (
          <div key={m.l} className="flex items-center gap-1.5">
            <span className="text-[18px] font-semibold" style={{ color: m.c, fontFamily: "DM Mono,monospace" }}>{m.v}</span>
            <span className="text-[11px] text-neutral-400">{m.l}</span>
          </div>
        ))}
        <div className="ml-auto flex gap-0.5">
          {["All","Critical","Overdue","AI Draft"].map((f, fi) => (
            <button key={f} className={`px-3 py-1.5 rounded-lg text-[11px] font-medium transition-colors ${fi === 0 ? "bg-neutral-900 text-white" : "text-neutral-500 hover:bg-neutral-100"}`}>{f}</button>
          ))}
        </div>
      </div>

      <div className="p-5 space-y-2.5">
        {APPROVALS.map(a => {
          const done    = approved.includes(a.id);
          const denied  = rejected.includes(a.id);
          const overdue = a.sla === "Overdue";
          const crit    = a.priority === "Critical";

          return (
            <div key={a.id} className={`bg-white rounded-xl border transition-all p-4 ${done ? "border-emerald-200 opacity-60" : denied ? "border-red-200 opacity-60" : crit ? "border-red-200/60" : overdue ? "border-amber-200/60" : "border-black/[0.06]"}`}>
              <div className="flex items-center gap-4">
                <div className="flex-1 grid grid-cols-5 gap-4 items-center min-w-0">
                  <div>
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="text-[10px] font-mono text-neutral-400">{a.id}</span>
                      {crit && <span className="text-[9px] font-bold text-red-600 bg-red-50 px-1.5 py-px rounded uppercase tracking-widest">Critical</span>}
                    </div>
                    <div className="text-[13px] font-semibold text-neutral-800">{a.type}</div>
                  </div>
                  <div>
                    <div className="text-[9px] uppercase tracking-widest text-neutral-400 mb-1">Employee</div>
                    <div className="flex items-center gap-1.5">
                      <Av name={a.employee} size="xs" />
                      <span className="text-[12px] font-medium text-neutral-700 truncate">{a.employee}</span>
                    </div>
                  </div>
                  <div>
                    <div className="text-[9px] uppercase tracking-widest text-neutral-400 mb-1">Manager</div>
                    <span className="text-[12px] text-neutral-600">{a.mgr}</span>
                  </div>
                  <div>
                    <div className="text-[9px] uppercase tracking-widest text-neutral-400 mb-1">Deadline · SLA</div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[11px] font-mono text-neutral-600">{a.deadline}</span>
                      <span className={`text-[10px] font-semibold ${overdue ? "text-red-600" : a.sla.includes("1d") ? "text-amber-600" : "text-neutral-400"}`}>{a.sla}</span>
                    </div>
                  </div>
                  <div>
                    <Chip status={done ? "Approved" : denied ? "Rejected" : a.status} />
                  </div>
                </div>

                <div className="flex items-center gap-1.5 flex-shrink-0">
                  {!done && !denied ? (
                    <>
                      {a.status === "AI Draft" && (
                        <button className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-medium text-violet-700 bg-violet-50 hover:bg-violet-100 border border-violet-200 transition-colors">
                          <Eye size={11} />Review
                        </button>
                      )}
                      <button onClick={() => approve(a.id)} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 transition-colors">
                        <Check size={11} />Approve
                      </button>
                      <button onClick={() => reject(a.id)} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-medium text-red-600 bg-red-50 hover:bg-red-100 border border-red-200 transition-colors">
                        <X size={11} />Reject
      </button>
                    </>
                  ) : (
                    <div className={`flex items-center gap-1 text-[11px] font-medium ${done ? "text-emerald-600" : "text-red-500"}`}>
                      {done ? <><Check size={13} />Approved</> : <><X size={13} />Rejected</>}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Root ─────────────────────────────────────────────────────────────────────
export default function App() {
  const [section, setSection] = useState<NavSection>("dashboard");

  const view = {
    dashboard:  <DashboardView />,
    reviews:    <ReviewsView />,
    goals:      <GoalsView />,
    career:     <CareerRoadmapView />,
    succession: <SuccessionView />,
    feedback:   <FeedbackView />,
    analytics:  <AnalyticsView />,
    approvals:  <ApprovalsView />,
  }[section];

  return (
    <div
      className="flex h-screen w-screen overflow-hidden"
      style={{ backgroundColor: "#F1F1F6", fontFamily: "Plus Jakarta Sans, sans-serif" }}
    >
      <Sidebar active={section} onChange={setSection} />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <TopBar section={section} />
        <main className="flex-1 overflow-hidden">{view}</main>
      </div>
    </div>
  );
}
