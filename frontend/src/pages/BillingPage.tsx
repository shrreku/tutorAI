import {
  CreditCard,
  TrendingDown,
  TrendingUp,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  Loader2,
  Download,
  Gauge,
  Coins,
} from 'lucide-react';
import { useBillingBalance, useBillingUsage } from '../api/hooks';
import type { CreditLedgerEntry } from '../types/api';

function entryTypeLabel(t: string) {
  const labels: Record<string, string> = {
    grant: 'Grant',
    reserve: 'Reserved',
    debit: 'Charged',
    release: 'Released',
    refund: 'Refund',
    expire: 'Expired',
  };
  return labels[t] ?? t;
}

function entryTypeColor(t: string) {
  if (t === 'grant' || t === 'release' || t === 'refund') return 'text-emerald-500';
  if (t === 'debit' || t === 'reserve' || t === 'expire') return 'text-red-400';
  return 'text-muted-foreground';
}

function formatNumber(n: number) {
  return n.toLocaleString();
}

function downloadCsv(entries: CreditLedgerEntry[]) {
  const header = 'Date,Type,Delta,Balance After,Reference Type,Reference ID\n';
  const rows = entries.map(
    (e) =>
      `${e.created_at},${e.entry_type},${e.delta},${e.balance_after},${e.reference_type ?? ''},${e.reference_id ?? ''}`
  );
  const blob = new Blob([header + rows.join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `studyagent-usage-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function BillingPage() {
  const { data: balance, isLoading: balanceLoading } = useBillingBalance();
  const { data: usage, isLoading: usageLoading } = useBillingUsage();

  if (balanceLoading || usageLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const creditsEnabled = balance?.credits_enabled ?? false;
  const softThreshold =
    (balance?.monthly_limit ?? 0) * (balance?.soft_limit_pct ?? 0.8);
  const isLowBalance =
    creditsEnabled && (balance?.balance ?? 0) < softThreshold * 0.2; // warn at 20% of soft
  const monthlyUsagePct = balance?.monthly_limit
    ? Math.min(100, Math.round(((balance.lifetime_used || 0) / balance.monthly_limit) * 100))
    : 0;

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      <div className="max-w-4xl animate-fade-up">
        <div className="flex items-center gap-2 mb-3">
          <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
          <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium">
            Billing
          </span>
        </div>
        <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight text-foreground leading-tight mb-2">
          Credits & <span className="italic text-gold">usage</span>
        </h1>
        <p className="text-muted-foreground max-w-2xl">
          Monitor your credit balance and usage history. Platform-managed tutoring,
          uploads, and background preparation consume credits. Live tutoring with a
          valid BYOK key bypasses platform billing.
        </p>
      </div>

      {!creditsEnabled && (
        <div className="max-w-4xl mt-8 rounded-xl border border-border bg-card p-6">
          <p className="text-muted-foreground text-sm">
            Credits system is currently disabled. All features are available without usage limits.
          </p>
        </div>
      )}

      {creditsEnabled && balance && (
        <div className="max-w-4xl mt-8 space-y-6">
          {/* Balance cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-2 mb-2">
                <CreditCard className="w-4 h-4 text-gold" />
                <span className="text-xs uppercase tracking-wider text-muted-foreground">
                  Balance
                </span>
              </div>
              <p className="text-2xl font-display font-semibold text-foreground">
                {formatNumber(balance.balance)}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                {balance.plan_tier.replace('_', ' ')} tier
              </p>
            </div>

            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-2 mb-2">
                <TrendingUp className="w-4 h-4 text-emerald-500" />
                <span className="text-xs uppercase tracking-wider text-muted-foreground">
                  Granted
                </span>
              </div>
              <p className="text-2xl font-display font-semibold text-foreground">
                {formatNumber(balance.lifetime_granted)}
              </p>
              <p className="text-xs text-muted-foreground mt-1">lifetime total</p>
            </div>

            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-2 mb-2">
                <TrendingDown className="w-4 h-4 text-red-400" />
                <span className="text-xs uppercase tracking-wider text-muted-foreground">
                  Used
                </span>
              </div>
              <p className="text-2xl font-display font-semibold text-foreground">
                {formatNumber(balance.lifetime_used)}
              </p>
              <p className="text-xs text-muted-foreground mt-1">lifetime total</p>
            </div>

            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-2 mb-2">
                <Coins className="w-4 h-4 text-gold" />
                <span className="text-xs uppercase tracking-wider text-muted-foreground">
                  Monthly grant
                </span>
              </div>
              <p className="text-2xl font-display font-semibold text-foreground">
                {formatNumber(balance.default_monthly_grant)}
              </p>
              <p className="text-xs text-muted-foreground mt-1">operator-managed refresh amount</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-2 mb-3">
                <Gauge className="w-4 h-4 text-gold" />
                <span className="text-xs uppercase tracking-wider text-muted-foreground">Limits</span>
              </div>
              <div className="space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Daily cap</span>
                  <span className="text-foreground font-medium">{formatNumber(balance.daily_limit)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Monthly cap</span>
                  <span className="text-foreground font-medium">{formatNumber(balance.monthly_limit)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Soft-limit warning</span>
                  <span className="text-foreground font-medium">{Math.round(balance.soft_limit_pct * 100)}%</span>
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs uppercase tracking-wider text-muted-foreground">Usage against monthly cap</span>
                <span className="text-sm font-medium text-foreground">{monthlyUsagePct}%</span>
              </div>
              <div className="h-2 rounded-full bg-background overflow-hidden">
                <div className="h-full rounded-full bg-gradient-to-r from-gold to-amber-400" style={{ width: `${monthlyUsagePct}%` }} />
              </div>
              <p className="text-xs text-muted-foreground mt-3">
                Tutoring with platform credentials, uploads, and queued notebook preparation draw from the same shared credit pool.
              </p>
            </div>
          </div>

          {/* Low balance warning */}
          {isLowBalance && (
            <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
              <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-foreground">Low credit balance</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Your balance is running low. You have {formatNumber(balance.balance)} credits
                  remaining. Monthly limit: {formatNumber(balance.monthly_limit)}.
                </p>
              </div>
            </div>
          )}

          <div className="rounded-xl border border-border bg-card p-5 text-sm text-muted-foreground">
            BYOK scope: your own key applies only to live tutoring requests. Uploads and queued notebook preparation always
            run on platform infrastructure so they can complete outside the browser request lifecycle.
          </div>

          {/* Usage history */}
          <div className="rounded-xl border border-border bg-card">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <h2 className="font-display text-lg font-semibold text-card-foreground">
                Recent activity
              </h2>
              {usage?.entries && usage.entries.length > 0 && (
                <button
                  onClick={() => downloadCsv(usage.entries)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-white/[0.04] transition-colors"
                >
                  <Download className="w-3.5 h-3.5" />
                  Export CSV
                </button>
              )}
            </div>

            {(!usage?.entries || usage.entries.length === 0) ? (
              <div className="px-5 py-8 text-center text-sm text-muted-foreground">
                No usage activity yet.
              </div>
            ) : (
              <div className="divide-y divide-border">
                {usage.entries.map((entry) => (
                  <div key={entry.id} className="px-5 py-3 flex items-center gap-4">
                    <div className="flex-shrink-0">
                      {entry.delta >= 0 ? (
                        <ArrowUpRight className="w-4 h-4 text-emerald-500" />
                      ) : (
                        <ArrowDownRight className="w-4 h-4 text-red-400" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground">
                        {entryTypeLabel(entry.entry_type)}
                        {entry.reference_type && (
                          <span className="text-muted-foreground font-normal">
                            {' '}
                            &middot; {entry.reference_type}
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(entry.created_at).toLocaleString()}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className={`text-sm font-medium ${entryTypeColor(entry.entry_type)}`}>
                        {entry.delta >= 0 ? '+' : ''}
                        {formatNumber(entry.delta)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        bal: {formatNumber(entry.balance_after)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
