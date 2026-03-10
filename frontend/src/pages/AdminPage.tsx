import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { Coins, Loader2, Search, Shield, UserRound, Wallet } from 'lucide-react';
import { ApiError } from '../api/client';
import { useAdminBillingOverview, useAdminGrant, useAdminMonthlyGrant } from '../api/hooks';

function formatNumber(value: number) {
  return value.toLocaleString();
}

export default function AdminPage() {
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search.trim());
  const { data, isLoading, error } = useAdminBillingOverview(deferredSearch || undefined);
  const adminGrant = useAdminGrant();
  const adminMonthlyGrant = useAdminMonthlyGrant();

  const users = useMemo(() => data?.users ?? [], [data?.users]);
  const [selectedUserId, setSelectedUserId] = useState('');
  const selectedUser = useMemo(
    () => users.find((user) => user.id === selectedUserId) ?? users[0] ?? null,
    [selectedUserId, users]
  );

  const [amount, setAmount] = useState('5000');
  const [memo, setMemo] = useState('Manual admin grant for support/testing');
  const [source, setSource] = useState('admin_topup');
  const [feedback, setFeedback] = useState<string | null>(null);
  const [monthlyGrantFeedback, setMonthlyGrantFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedUserId && users[0]) {
      setSelectedUserId(users[0].id);
    }
    if (selectedUserId && !users.some((user) => user.id === selectedUserId)) {
      setSelectedUserId(users[0]?.id ?? '');
    }
  }, [selectedUserId, users]);

  const handleGrant = async () => {
    if (!selectedUser) {
      return;
    }

    setFeedback(null);
    try {
      const response = await adminGrant.mutateAsync({
        user_id: selectedUser.id,
        amount: Number(amount),
        memo,
        source,
      });
      setFeedback(`Granted ${formatNumber(response.amount)} credits. New balance: ${formatNumber(response.new_balance)}.`);
    } catch (grantError) {
      const message = grantError instanceof ApiError ? grantError.message : 'Failed to grant credits.';
      setFeedback(message);
    }
  };

  const loadError = error instanceof ApiError ? error.message : null;

  const handleMonthlyGrant = async () => {
    setMonthlyGrantFeedback(null);
    try {
      const response = await adminMonthlyGrant.mutateAsync({});
      setMonthlyGrantFeedback(
        `Monthly grant refresh for ${response.period_key}: granted ${response.granted_user_count} users, skipped ${response.skipped_user_count}.`
      );
    } catch (grantError) {
      const message = grantError instanceof ApiError ? grantError.message : 'Failed to run monthly grant refresh.';
      setMonthlyGrantFeedback(message);
    }
  };

  return (
    <div className="h-full flex flex-col p-8 overflow-auto">
      <div className="max-w-6xl animate-fade-up">
        <div className="flex items-center gap-2 mb-3">
          <div className="h-px flex-1 max-w-[40px] bg-gold/40" />
          <span className="text-[11px] uppercase tracking-[0.25em] text-gold font-medium">
            Admin
          </span>
        </div>
        <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight text-foreground leading-tight mb-2">
          Credit <span className="italic text-gold">operations</span>
        </h1>
        <p className="text-muted-foreground max-w-3xl">
          Only one configured admin identity can access this panel. Use it to audit balances and issue explicit, memo-backed credit grants.
        </p>
      </div>

      <div className="max-w-6xl mt-8 grid gap-6 xl:grid-cols-[1.5fr,1fr]">
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div>
              <p className="text-sm font-medium text-foreground">Account search</p>
              <p className="text-xs text-muted-foreground mt-1">
                Configured admin: {data?.configured_admin_external_id ?? 'not configured'}
              </p>
            </div>
            <label className="relative block w-full max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search email, name, or identity"
                className="w-full rounded-lg border border-border bg-background pl-9 pr-3 py-2 text-sm"
              />
            </label>
          </div>

          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading accounts...
            </div>
          ) : loadError ? (
            <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {loadError}
            </div>
          ) : users.length === 0 ? (
            <div className="rounded-lg border border-border/70 bg-background/40 px-4 py-6 text-sm text-muted-foreground">
              No accounts matched this query.
            </div>
          ) : (
            <div className="space-y-3">
              {users.map((user) => {
                const isSelected = selectedUser?.id === user.id;
                return (
                  <button
                    key={user.id}
                    type="button"
                    onClick={() => setSelectedUserId(user.id)}
                    className={`w-full rounded-xl border p-4 text-left transition-colors ${isSelected ? 'border-gold/30 bg-gold/10' : 'border-border bg-background/30 hover:bg-background/50'}`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <UserRound className="w-4 h-4 text-gold" />
                          <p className="text-sm font-medium text-foreground">
                            {user.display_name || user.email || user.external_id || user.id}
                          </p>
                          {user.is_admin && (
                            <span className="inline-flex items-center gap-1 rounded-full border border-gold/30 bg-gold/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-gold">
                              <Shield className="w-3 h-3" /> Sole admin
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">{user.email || user.external_id || user.id}</p>
                        <p className="text-xs text-muted-foreground mt-1">Joined {new Date(user.created_at).toLocaleString()}</p>
                      </div>
                      <div className="grid grid-cols-3 gap-3 text-right min-w-[260px]">
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Balance</p>
                          <p className="text-sm font-semibold text-foreground">{formatNumber(user.balance)}</p>
                        </div>
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Granted</p>
                          <p className="text-sm font-semibold text-emerald-400">{formatNumber(user.lifetime_granted)}</p>
                        </div>
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Used</p>
                          <p className="text-sm font-semibold text-red-300">{formatNumber(user.lifetime_used)}</p>
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-border bg-card p-5 h-fit">
          <div className="rounded-lg border border-border/70 bg-background/40 p-4 mb-4">
            <p className="text-sm font-medium text-foreground">Default grant policy</p>
            <p className="text-xs text-muted-foreground mt-1">
              Signup grant: {formatNumber(data?.default_monthly_grant ?? 0)} credits. Monthly operator refresh period: {data?.current_grant_period ?? 'current'}.
            </p>
            <button
              type="button"
              onClick={handleMonthlyGrant}
              disabled={adminMonthlyGrant.isPending}
              className="mt-3 inline-flex items-center gap-2 rounded-lg border border-gold/20 bg-gold/10 px-3 py-2 text-sm font-medium text-gold disabled:opacity-50"
            >
              {adminMonthlyGrant.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Coins className="w-4 h-4" />}
              Run monthly grant refresh
            </button>
            {monthlyGrantFeedback && (
              <div className={`mt-3 rounded-lg border px-3 py-2 text-sm ${monthlyGrantFeedback.includes('Failed') ? 'border-red-500/20 bg-red-500/10 text-red-200' : 'border-gold/20 bg-gold/10 text-gold'}`}>
                {monthlyGrantFeedback}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 mb-4">
            <Coins className="w-4 h-4 text-gold" />
            <p className="text-sm font-medium text-foreground">Grant credits</p>
          </div>

          {selectedUser ? (
            <div className="space-y-4">
              <div className="rounded-lg border border-border/70 bg-background/40 p-4">
                <p className="text-sm font-medium text-foreground">{selectedUser.display_name || selectedUser.email || selectedUser.id}</p>
                <p className="text-xs text-muted-foreground mt-1">{selectedUser.email || selectedUser.external_id || selectedUser.id}</p>
                <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                  <Wallet className="w-3.5 h-3.5" /> Current balance: {formatNumber(selectedUser.balance)}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">Amount</label>
                <input
                  type="number"
                  min="1"
                  max="250000"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">Source</label>
                <select
                  value={source}
                  onChange={(event) => setSource(event.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                >
                  <option value="admin_topup">Admin top-up</option>
                  <option value="promo_grant">Promo grant</option>
                  <option value="support_refill">Support refill</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">Memo</label>
                <textarea
                  value={memo}
                  onChange={(event) => setMemo(event.target.value)}
                  rows={4}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                />
              </div>

              <button
                type="button"
                onClick={handleGrant}
                disabled={adminGrant.isPending || !selectedUser || !amount || !memo.trim()}
                className="inline-flex items-center gap-2 rounded-lg bg-gold px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                {adminGrant.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Coins className="w-4 h-4" />}
                Issue grant
              </button>

              {feedback && (
                <div className={`rounded-lg border px-3 py-2 text-sm ${feedback.includes('Failed') ? 'border-red-500/20 bg-red-500/10 text-red-200' : 'border-gold/20 bg-gold/10 text-gold'}`}>
                  {feedback}
                </div>
              )}

              <p className="text-xs text-muted-foreground">
                Abuse control: only the configured admin can reach this page, every grant requires a memo, and backend audit metadata records who issued it.
              </p>
            </div>
          ) : (
            <div className="rounded-lg border border-border/70 bg-background/40 px-4 py-6 text-sm text-muted-foreground">
              Select an account to grant credits.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}