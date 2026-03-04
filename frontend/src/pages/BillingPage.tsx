import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import {
  CreditCard,
  TrendingDown,
  TrendingUp,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  Loader2,
  Download,
} from 'lucide-react';

// Types matching backend billing schemas
interface BalanceData {
  credits_enabled: boolean;
  balance: number;
  lifetime_granted: number;
  lifetime_used: number;
  plan_tier: string;
  daily_limit: number;
  monthly_limit: number;
  soft_limit_pct: number;
}

interface LedgerEntry {
  id: string;
  entry_type: string;
  delta: number;
  balance_after: number;
  reference_type: string | null;
  reference_id: string | null;
  created_at: string;
}

interface UsageHistory {
  credits_enabled: boolean;
  entries: LedgerEntry[];
}

function useBalance() {
  return useQuery({
    queryKey: ['billing', 'balance'],
    queryFn: () => apiClient.get<BalanceData>('/billing/balance'),
  });
}

function useUsageHistory(limit = 50) {
  return useQuery({
    queryKey: ['billing', 'usage', limit],
    queryFn: () =>
      apiClient.get<UsageHistory>('/billing/usage', {
        limit: limit.toString(),
      }),
  });
}

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

function downloadCsv(entries: LedgerEntry[]) {
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
  const { data: balance, isLoading: balanceLoading } = useBalance();
  const { data: usage, isLoading: usageLoading } = useUsageHistory();

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
          Monitor your credit balance and usage history. Credits are used for
          tutoring turns and document ingestion.
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
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
