import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { Coins, Loader2, Search, Shield, UserRound, Wallet, Cpu, Activity, FileText } from 'lucide-react';
import { ApiError } from '../api/client';
import {
  useAdminBillingOverview,
  useAdminGrant,
  useAdminMonthlyGrant,
  useAdminModelPricing,
  useAdminTaskAssignments,
  useAdminModelHealth,
  useAdminHealthAction,
  useAdminPageAllowanceGrant,
  useAdminCreateModelPricing,
  useAdminUpdateModelPricing,
  useAdminDeactivateModelPricing,
  useAdminCreateTaskAssignment,
  useAdminUpdateTaskAssignment,
} from '../api/hooks';
import { formatCredits } from '../lib/credits';

function parseCsvList(value: string) {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinCsvList(values: string[] | undefined | null) {
  return (values ?? []).join(', ');
}

export default function AdminPage() {
  const [search, setSearch] = useState('');
  const deferredSearch = useDeferredValue(search.trim());
  const { data, isLoading, error } = useAdminBillingOverview(deferredSearch || undefined);
  const adminGrant = useAdminGrant();
  const adminPageAllowanceGrant = useAdminPageAllowanceGrant();
  const adminMonthlyGrant = useAdminMonthlyGrant();
  const { data: modelPricing } = useAdminModelPricing();
  const { data: taskAssignments } = useAdminTaskAssignments();
  const { data: modelHealth } = useAdminModelHealth();
  const healthAction = useAdminHealthAction();
  const createModelPricing = useAdminCreateModelPricing();
  const [selectedPricingModelId, setSelectedPricingModelId] = useState('');
  const updateModelPricing = useAdminUpdateModelPricing(selectedPricingModelId || '__new__');
  const deactivateModelPricing = useAdminDeactivateModelPricing();
  const createTaskAssignment = useAdminCreateTaskAssignment();
  const [selectedAssignmentTaskType, setSelectedAssignmentTaskType] = useState('');
  const updateTaskAssignment = useAdminUpdateTaskAssignment(selectedAssignmentTaskType || '__new__');
  const [healthFeedback, setHealthFeedback] = useState<string | null>(null);
  const [pricingFeedback, setPricingFeedback] = useState<string | null>(null);
  const [, setAssignmentFeedback] = useState<string | null>(null);
  const [pricingDraft, setPricingDraft] = useState({
    model_id: '',
    provider_name: '',
    display_name: '',
    model_class: 'standard',
    input_usd_per_million: '0',
    output_usd_per_million: '0',
    cache_write_usd_per_million: '',
    cache_read_usd_per_million: '',
    is_active: true,
    is_user_selectable: true,
    supports_structured_output: false,
    supports_long_context: false,
    supports_byok: false,
    notes: '',
  });
  const [assignmentDraft, setAssignmentDraft] = useState({
    task_type: '',
    default_model_id: '',
    fallback_model_ids: '',
    allowed_model_ids: '',
    user_override_allowed: false,
    rollout_state: 'active',
    beta_only: false,
  });

  const users = useMemo(() => data?.users ?? [], [data?.users]);
  const [selectedUserId, setSelectedUserId] = useState('');
  const selectedUser = useMemo(
    () => users.find((user) => user.id === selectedUserId) ?? users[0] ?? null,
    [selectedUserId, users]
  );

  const [amount, setAmount] = useState('50');
  const [memo, setMemo] = useState('Manual admin grant for support/testing');
  const [source, setSource] = useState('admin_topup');
  const [feedback, setFeedback] = useState<string | null>(null);
  const [pageAmount, setPageAmount] = useState('200');
  const [pageMemo, setPageMemo] = useState('Manual parse page allowance increase');
  const [pageFeedback, setPageFeedback] = useState<string | null>(null);
  const [monthlyGrantFeedback, setMonthlyGrantFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedUserId && users[0]) {
      setSelectedUserId(users[0].id);
    }
    if (selectedUserId && !users.some((user) => user.id === selectedUserId)) {
      setSelectedUserId(users[0]?.id ?? '');
    }
  }, [selectedUserId, users]);

  useEffect(() => {
    if (!selectedPricingModelId && modelPricing?.[0]) {
      setSelectedPricingModelId(modelPricing[0].model_id);
    }
  }, [modelPricing, selectedPricingModelId]);

  useEffect(() => {
    if (!selectedAssignmentTaskType && taskAssignments?.[0]) {
      setSelectedAssignmentTaskType(taskAssignments[0].task_type);
    }
  }, [taskAssignments, selectedAssignmentTaskType]);

  useEffect(() => {
    const selected = modelPricing?.find((model) => model.model_id === selectedPricingModelId);
    if (!selected) return;
    setPricingDraft({
      model_id: selected.model_id,
      provider_name: selected.provider_name,
      display_name: selected.display_name,
      model_class: selected.model_class,
      input_usd_per_million: String(selected.input_usd_per_million),
      output_usd_per_million: String(selected.output_usd_per_million),
      cache_write_usd_per_million: selected.cache_write_usd_per_million?.toString() ?? '',
      cache_read_usd_per_million: selected.cache_read_usd_per_million?.toString() ?? '',
      is_active: selected.is_active,
      is_user_selectable: selected.is_user_selectable,
      supports_structured_output: selected.supports_structured_output,
      supports_long_context: selected.supports_long_context,
      supports_byok: false,
      notes: selected.notes ?? '',
    });
  }, [modelPricing, selectedPricingModelId]);

  useEffect(() => {
    const selected = taskAssignments?.find((assignment) => assignment.task_type === selectedAssignmentTaskType);
    if (!selected) return;
    setAssignmentDraft({
      task_type: selected.task_type,
      default_model_id: selected.default_model_id,
      fallback_model_ids: joinCsvList(selected.fallback_model_ids),
      allowed_model_ids: joinCsvList(selected.allowed_model_ids),
      user_override_allowed: selected.user_override_allowed,
      rollout_state: selected.rollout_state,
      beta_only: selected.beta_only,
    });
  }, [selectedAssignmentTaskType, taskAssignments]);

  const handleGrant = async () => {
    if (!selectedUser) {
      return;
    }

    setFeedback(null);
    try {
      const response = await adminGrant.mutateAsync({
        user_id: selectedUser.id,
        amount: Math.round(Number(amount) * 100),
        memo,
        source,
      });
      setFeedback(`Granted ${formatCredits(response.amount)} credits. New balance: ${formatCredits(response.new_balance)}.`);
    } catch (grantError) {
      const message = grantError instanceof ApiError ? grantError.message : 'Failed to grant credits.';
      setFeedback(message);
    }
  };

  const handlePageGrant = async () => {
    if (!selectedUser) {
      return;
    }

    setPageFeedback(null);
    try {
      const response = await adminPageAllowanceGrant.mutateAsync({
        user_id: selectedUser.id,
        amount: Math.round(Number(pageAmount)),
        memo: pageMemo,
      });
      setPageFeedback(`Granted ${response.amount} pages. New limit: ${response.new_limit}. Remaining pages: ${response.remaining_pages}.`);
    } catch (grantError) {
      const message = grantError instanceof ApiError ? grantError.message : 'Failed to grant parse pages.';
      setPageFeedback(message);
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

  const resetPricingDraft = () => {
    setSelectedPricingModelId('');
    setPricingDraft({
      model_id: '',
      provider_name: '',
      display_name: '',
      model_class: 'standard',
      input_usd_per_million: '0',
      output_usd_per_million: '0',
      cache_write_usd_per_million: '',
      cache_read_usd_per_million: '',
      is_active: true,
      is_user_selectable: true,
      supports_structured_output: false,
      supports_long_context: false,
      supports_byok: false,
      notes: '',
    });
  };

  const resetAssignmentDraft = () => {
    setSelectedAssignmentTaskType('');
    setAssignmentDraft({
      task_type: '',
      default_model_id: '',
      fallback_model_ids: '',
      allowed_model_ids: '',
      user_override_allowed: false,
      rollout_state: 'active',
      beta_only: false,
    });
  };

  const handleSavePricing = async () => {
    setPricingFeedback(null);
    const request = {
      model_id: pricingDraft.model_id.trim(),
      provider_name: pricingDraft.provider_name.trim(),
      display_name: pricingDraft.display_name.trim(),
      model_class: pricingDraft.model_class.trim(),
      input_usd_per_million: Number(pricingDraft.input_usd_per_million),
      output_usd_per_million: Number(pricingDraft.output_usd_per_million),
      cache_write_usd_per_million: pricingDraft.cache_write_usd_per_million ? Number(pricingDraft.cache_write_usd_per_million) : null,
      cache_read_usd_per_million: pricingDraft.cache_read_usd_per_million ? Number(pricingDraft.cache_read_usd_per_million) : null,
      is_active: pricingDraft.is_active,
      is_user_selectable: pricingDraft.is_user_selectable,
      supports_structured_output: pricingDraft.supports_structured_output,
      supports_long_context: pricingDraft.supports_long_context,
      supports_byok: pricingDraft.supports_byok,
      notes: pricingDraft.notes.trim() || null,
    };

    try {
      if (!request.model_id || !request.provider_name || !request.display_name) {
        throw new Error('Model id, provider name, and display name are required.');
      }
      if (modelPricing?.some((model) => model.model_id === request.model_id)) {
        await updateModelPricing.mutateAsync({
          input_usd_per_million: request.input_usd_per_million,
          output_usd_per_million: request.output_usd_per_million,
          is_active: request.is_active,
          is_user_selectable: request.is_user_selectable,
          notes: request.notes,
        });
        setPricingFeedback(`Updated ${request.model_id}.`);
      } else {
        await createModelPricing.mutateAsync(request);
        setPricingFeedback(`Created ${request.model_id}.`);
      }
    } catch (error) {
      setPricingFeedback(error instanceof ApiError ? error.message : (error instanceof Error ? error.message : 'Failed to save model.'));
    }
  };

  const handleDeactivatePricing = async () => {
    if (!pricingDraft.model_id.trim()) return;
    setPricingFeedback(null);
    try {
      await deactivateModelPricing.mutateAsync(pricingDraft.model_id.trim());
      setPricingFeedback(`Deactivated ${pricingDraft.model_id.trim()}.`);
    } catch (error) {
      setPricingFeedback(error instanceof ApiError ? error.message : 'Failed to deactivate model.');
    }
  };

  const handleSaveAssignment = async () => {
    setAssignmentFeedback(null);
    const request = {
      task_type: assignmentDraft.task_type.trim(),
      default_model_id: assignmentDraft.default_model_id.trim(),
      fallback_model_ids: parseCsvList(assignmentDraft.fallback_model_ids),
      allowed_model_ids: parseCsvList(assignmentDraft.allowed_model_ids),
      user_override_allowed: assignmentDraft.user_override_allowed,
      rollout_state: assignmentDraft.rollout_state.trim(),
      beta_only: assignmentDraft.beta_only,
    };

    try {
      if (!request.task_type || !request.default_model_id) {
        throw new Error('Task type and default model are required.');
      }
      if (taskAssignments?.some((assignment) => assignment.task_type === request.task_type)) {
        await updateTaskAssignment.mutateAsync({
          default_model_id: request.default_model_id,
          fallback_model_ids: request.fallback_model_ids,
          allowed_model_ids: request.allowed_model_ids,
          user_override_allowed: request.user_override_allowed,
          rollout_state: request.rollout_state,
        });
        setAssignmentFeedback(`Updated ${request.task_type}.`);
      } else {
        await createTaskAssignment.mutateAsync(request);
        setAssignmentFeedback(`Created ${request.task_type}.`);
      }
    } catch (error) {
      setAssignmentFeedback(error instanceof ApiError ? error.message : (error instanceof Error ? error.message : 'Failed to save assignment.'));
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
          Only one configured admin identity can access this panel. Use it to audit balances, parse page allowance, and issue explicit memo-backed grants.
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
                          <p className="text-sm font-semibold text-foreground">{formatCredits(user.balance)}</p>
                        </div>
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Granted</p>
                          <p className="text-sm font-semibold text-emerald-400">{formatCredits(user.lifetime_granted)}</p>
                        </div>
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Used</p>
                          <p className="text-sm font-semibold text-red-300">{formatCredits(user.lifetime_used)}</p>
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 grid grid-cols-4 gap-3 text-right min-w-[260px]">
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Pages left</p>
                        <p className="text-sm font-semibold text-foreground">{user.parse_page_remaining}</p>
                      </div>
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Limit</p>
                        <p className="text-sm font-semibold text-foreground">{user.parse_page_limit}</p>
                      </div>
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Used</p>
                        <p className="text-sm font-semibold text-red-300">{user.parse_page_used}</p>
                      </div>
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Reserved</p>
                        <p className="text-sm font-semibold text-gold">{user.parse_page_reserved}</p>
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
              Monthly refresh amount: {formatCredits(data?.default_monthly_grant ?? 0)} credits. Monthly operator refresh period: {data?.current_grant_period ?? 'current'}.
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Default parse allowance for new users: {data?.default_page_allowance ?? 0} pages.
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
                  <Wallet className="w-3.5 h-3.5" /> Current balance: {formatCredits(selectedUser.balance)}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5"><FileText className="w-3.5 h-3.5" /> Remaining pages: {selectedUser.parse_page_remaining}</span>
                  <span>Limit: {selectedUser.parse_page_limit}</span>
                  <span>Used: {selectedUser.parse_page_used}</span>
                  <span>Reserved: {selectedUser.parse_page_reserved}</span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">Amount</label>
                <input
                  type="number"
                  min="0.5"
                  max="2500"
                  step="0.5"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                />
                <p className="mt-1 text-xs text-muted-foreground">Enter credits here. The API stores 100 internal units per credit.</p>
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

              <div className="pt-2 border-t border-border/60">
                <div className="flex items-center gap-2 mb-4">
                  <FileText className="w-4 h-4 text-gold" />
                  <p className="text-sm font-medium text-foreground">Grant parse pages</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-foreground mb-1.5">Pages</label>
                  <input
                    type="number"
                    min="1"
                    max="20000"
                    step="1"
                    value={pageAmount}
                    onChange={(event) => setPageAmount(event.target.value)}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  />
                </div>

                <div className="mt-4">
                  <label className="block text-sm font-medium text-foreground mb-1.5">Memo</label>
                  <textarea
                    value={pageMemo}
                    onChange={(event) => setPageMemo(event.target.value)}
                    rows={3}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  />
                </div>

                <button
                  type="button"
                  onClick={handlePageGrant}
                  disabled={adminPageAllowanceGrant.isPending || !selectedUser || !pageAmount || !pageMemo.trim()}
                  className="mt-4 inline-flex items-center gap-2 rounded-lg border border-gold/20 bg-gold/10 px-4 py-2 text-sm font-medium text-gold disabled:opacity-50"
                >
                  {adminPageAllowanceGrant.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                  Increase page allowance
                </button>

                {pageFeedback && (
                  <div className={`mt-3 rounded-lg border px-3 py-2 text-sm ${pageFeedback.includes('Failed') ? 'border-red-500/20 bg-red-500/10 text-red-200' : 'border-gold/20 bg-gold/10 text-gold'}`}>
                    {pageFeedback}
                  </div>
                )}
              </div>

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

      {/* CM-017: Model & Health Management */}
      <div className="max-w-6xl mt-8 space-y-6">
        <div className="flex items-center gap-2">
          <Cpu className="w-5 h-5 text-gold" />
          <h2 className="font-display text-xl font-semibold text-foreground">Model registry & health</h2>
        </div>

        {healthFeedback && (
          <div className={`rounded-lg border px-3 py-2 text-sm ${healthFeedback.includes('Failed') ? 'border-red-500/20 bg-red-500/10 text-red-200' : 'border-gold/20 bg-gold/10 text-gold'}`}>
            {healthFeedback}
          </div>
        )}

        {pricingFeedback && (
          <div className={`rounded-lg border px-3 py-2 text-sm ${pricingFeedback.includes('Failed') ? 'border-red-500/20 bg-red-500/10 text-red-200' : 'border-gold/20 bg-gold/10 text-gold'}`}>
            {pricingFeedback}
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center justify-between gap-3 mb-4">
              <div>
                <h3 className="text-sm font-semibold text-foreground">Model editor</h3>
                <p className="text-xs text-muted-foreground mt-1">Create a model row or load one from the table to edit it.</p>
              </div>
              <button
                type="button"
                onClick={resetPricingDraft}
                className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
              >
                New model
              </button>
            </div>

            <div className="space-y-3">
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Model id</label>
                  <input
                    value={pricingDraft.model_id}
                    onChange={(event) => setPricingDraft((draft) => ({ ...draft, model_id: event.target.value }))}
                    disabled={Boolean(selectedPricingModelId)}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                    placeholder="provider/model-name"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Provider</label>
                  <input
                    value={pricingDraft.provider_name}
                    onChange={(event) => setPricingDraft((draft) => ({ ...draft, provider_name: event.target.value }))}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                    placeholder="openai"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Display name</label>
                <input
                  value={pricingDraft.display_name}
                  onChange={(event) => setPricingDraft((draft) => ({ ...draft, display_name: event.target.value }))}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  placeholder="GPT-4.1 Mini"
                />
              </div>

              <div className="grid gap-3 md:grid-cols-3">
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Class</label>
                  <select
                    value={pricingDraft.model_class}
                    onChange={(event) => setPricingDraft((draft) => ({ ...draft, model_class: event.target.value }))}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  >
                    <option value="economy">economy</option>
                    <option value="standard">standard</option>
                    <option value="premium_small">premium_small</option>
                    <option value="premium">premium</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Input $/1M</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={pricingDraft.input_usd_per_million}
                    onChange={(event) => setPricingDraft((draft) => ({ ...draft, input_usd_per_million: event.target.value }))}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Output $/1M</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={pricingDraft.output_usd_per_million}
                    onChange={(event) => setPricingDraft((draft) => ({ ...draft, output_usd_per_million: event.target.value }))}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  />
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Cache write $/1M</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={pricingDraft.cache_write_usd_per_million}
                    onChange={(event) => setPricingDraft((draft) => ({ ...draft, cache_write_usd_per_million: event.target.value }))}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Cache read $/1M</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={pricingDraft.cache_read_usd_per_million}
                    onChange={(event) => setPricingDraft((draft) => ({ ...draft, cache_read_usd_per_million: event.target.value }))}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  />
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-3 text-sm">
                <label className="inline-flex items-center gap-2 text-muted-foreground"><input type="checkbox" checked={pricingDraft.is_active} onChange={(event) => setPricingDraft((draft) => ({ ...draft, is_active: event.target.checked }))} /> Active</label>
                <label className="inline-flex items-center gap-2 text-muted-foreground"><input type="checkbox" checked={pricingDraft.is_user_selectable} onChange={(event) => setPricingDraft((draft) => ({ ...draft, is_user_selectable: event.target.checked }))} /> Selectable</label>
                <label className="inline-flex items-center gap-2 text-muted-foreground"><input type="checkbox" checked={pricingDraft.supports_structured_output} onChange={(event) => setPricingDraft((draft) => ({ ...draft, supports_structured_output: event.target.checked }))} /> Structured</label>
                <label className="inline-flex items-center gap-2 text-muted-foreground"><input type="checkbox" checked={pricingDraft.supports_long_context} onChange={(event) => setPricingDraft((draft) => ({ ...draft, supports_long_context: event.target.checked }))} /> Long context</label>
                <label className="inline-flex items-center gap-2 text-muted-foreground"><input type="checkbox" checked={pricingDraft.supports_byok} onChange={(event) => setPricingDraft((draft) => ({ ...draft, supports_byok: event.target.checked }))} /> BYOK</label>
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Notes</label>
                <textarea
                  value={pricingDraft.notes}
                  onChange={(event) => setPricingDraft((draft) => ({ ...draft, notes: event.target.value }))}
                  rows={3}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                />
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleSavePricing}
                  disabled={createModelPricing.isPending || updateModelPricing.isPending}
                  className="inline-flex items-center gap-2 rounded-lg bg-gold px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
                >
                  {(createModelPricing.isPending || updateModelPricing.isPending) ? <Loader2 className="w-4 h-4 animate-spin" /> : <Cpu className="w-4 h-4" />}
                  Save model
                </button>
                <button
                  type="button"
                  onClick={handleDeactivatePricing}
                  disabled={deactivateModelPricing.isPending || !pricingDraft.model_id.trim()}
                  className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-200 disabled:opacity-50"
                >
                  Deactivate
                </button>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center justify-between gap-3 mb-4">
              <div>
                <h3 className="text-sm font-semibold text-foreground">Task assignment editor</h3>
                <p className="text-xs text-muted-foreground mt-1">Create or edit a task scope, defaults, and allowed models.</p>
              </div>
              <button
                type="button"
                onClick={resetAssignmentDraft}
                className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
              >
                New assignment
              </button>
            </div>

            <div className="space-y-3">
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Task type</label>
                  <input
                    value={assignmentDraft.task_type}
                    onChange={(event) => setAssignmentDraft((draft) => ({ ...draft, task_type: event.target.value }))}
                    disabled={Boolean(selectedAssignmentTaskType)}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                    placeholder="artifact_generation"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Default model</label>
                  <select
                    value={assignmentDraft.default_model_id}
                    onChange={(event) => setAssignmentDraft((draft) => ({ ...draft, default_model_id: event.target.value }))}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  >
                    <option value="">Select default</option>
                    {(modelPricing ?? []).map((model) => (
                      <option key={model.model_id} value={model.model_id}>{model.display_name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Allowed model ids</label>
                <textarea
                  value={assignmentDraft.allowed_model_ids}
                  onChange={(event) => setAssignmentDraft((draft) => ({ ...draft, allowed_model_ids: event.target.value }))}
                  rows={2}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  placeholder="openai/gpt-4.1-mini, anthropic/claude-sonnet-4"
                />
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Fallback model ids</label>
                <textarea
                  value={assignmentDraft.fallback_model_ids}
                  onChange={(event) => setAssignmentDraft((draft) => ({ ...draft, fallback_model_ids: event.target.value }))}
                  rows={2}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  placeholder="openai/gpt-4.1-mini"
                />
              </div>

              <div className="grid gap-3 md:grid-cols-3 text-sm">
                <label className="inline-flex items-center gap-2 text-muted-foreground"><input type="checkbox" checked={assignmentDraft.user_override_allowed} onChange={(event) => setAssignmentDraft((draft) => ({ ...draft, user_override_allowed: event.target.checked }))} /> User override</label>
                <label className="inline-flex items-center gap-2 text-muted-foreground"><input type="checkbox" checked={assignmentDraft.beta_only} onChange={(event) => setAssignmentDraft((draft) => ({ ...draft, beta_only: event.target.checked }))} /> Beta only</label>
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground mb-1">Rollout</label>
                  <select
                    value={assignmentDraft.rollout_state}
                    onChange={(event) => setAssignmentDraft((draft) => ({ ...draft, rollout_state: event.target.value }))}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  >
                    <option value="active">active</option>
                    <option value="beta">beta</option>
                    <option value="disabled">disabled</option>
                  </select>
                </div>
              </div>

              <button
                type="button"
                onClick={handleSaveAssignment}
                disabled={createTaskAssignment.isPending || updateTaskAssignment.isPending}
                className="inline-flex items-center gap-2 rounded-lg bg-gold px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                {(createTaskAssignment.isPending || updateTaskAssignment.isPending) ? <Loader2 className="w-4 h-4 animate-spin" /> : <Cpu className="w-4 h-4" />}
                Save assignment
              </button>
            </div>
          </div>
        </div>

        {/* Pricing table */}
        {modelPricing && modelPricing.length > 0 && (
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <div className="px-5 py-4 border-b border-border/50">
              <h3 className="text-sm font-semibold text-foreground">Model pricing</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/50 text-xs text-muted-foreground uppercase tracking-wider">
                    <th className="px-4 py-2.5 text-left">Model</th>
                    <th className="px-4 py-2.5 text-left">Class</th>
                    <th className="px-4 py-2.5 text-right">Input $/1M</th>
                    <th className="px-4 py-2.5 text-right">Output $/1M</th>
                    <th className="px-4 py-2.5 text-center">Active</th>
                    <th className="px-4 py-2.5 text-center">Selectable</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {modelPricing.map((m) => (
                    <tr key={m.model_id} className="hover:bg-muted/30 cursor-pointer" onClick={() => setSelectedPricingModelId(m.model_id)}>
                      <td className="px-4 py-2.5 font-medium text-foreground">{m.display_name}</td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${m.model_class === 'economy' ? 'bg-emerald-500/10 text-emerald-400' : m.model_class === 'standard' ? 'bg-blue-500/10 text-blue-400' : 'bg-purple-500/10 text-purple-400'}`}>
                          {m.model_class}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-muted-foreground">${m.input_usd_per_million.toFixed(2)}</td>
                      <td className="px-4 py-2.5 text-right text-muted-foreground">${m.output_usd_per_million.toFixed(2)}</td>
                      <td className="px-4 py-2.5 text-center">{m.is_active ? '✓' : '—'}</td>
                      <td className="px-4 py-2.5 text-center">{m.is_user_selectable ? '✓' : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Task assignments */}
        {taskAssignments && taskAssignments.length > 0 && (
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <div className="px-5 py-4 border-b border-border/50">
              <h3 className="text-sm font-semibold text-foreground">Task → model assignments</h3>
            </div>
            <div className="divide-y divide-border/50">
              {taskAssignments.map((a) => (
                <button key={a.task_type} type="button" onClick={() => setSelectedAssignmentTaskType(a.task_type)} className="w-full px-5 py-3 flex items-center justify-between text-left hover:bg-muted/30">
                  <div>
                    <p className="text-sm font-medium text-foreground">{a.task_type}</p>
                    <p className="text-xs text-muted-foreground">Default: {a.default_model_id} · Fallbacks: {a.fallback_model_ids?.join(', ') || 'none'}</p>
                  </div>
                  <span className={`text-xs font-medium ${a.rollout_state === 'ga' ? 'text-emerald-400' : a.rollout_state === 'canary' ? 'text-amber-400' : 'text-muted-foreground'}`}>
                    {a.rollout_state}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Health grid */}
        {modelHealth && modelHealth.length > 0 && (
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <div className="px-5 py-4 border-b border-border/50">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <Activity className="w-4 h-4 text-gold" /> Model-task health
              </h3>
            </div>
            <div className="divide-y divide-border/50">
              {modelHealth.map((h) => (
                <div key={`${h.model_id}-${h.task_type}`} className="px-5 py-3 flex items-center gap-4">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-foreground">{h.model_id} · {h.task_type}</p>
                    <p className="text-xs text-muted-foreground">
                      Errors: {h.consecutive_errors} · Status: {h.status}
                      {h.cooldown_until && ` · Cooldown until ${new Date(h.cooldown_until).toLocaleTimeString()}`}
                    </p>
                  </div>
                  <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase ${h.status === 'healthy' ? 'bg-emerald-500/10 text-emerald-400' : h.status === 'degraded' ? 'bg-amber-500/10 text-amber-400' : 'bg-red-500/10 text-red-400'}`}>
                    {h.status}
                  </span>
                  {h.status !== 'healthy' && (
                    <button
                      onClick={async () => {
                        setHealthFeedback(null);
                        try {
                          await healthAction.mutateAsync({ action: 'clear-cooldown', model_id: h.model_id, task_type: h.task_type });
                          setHealthFeedback(`Cleared cooldown for ${h.model_id} · ${h.task_type}`);
                        } catch (err) {
                          setHealthFeedback(`Failed: ${err instanceof ApiError ? err.message : 'Unknown error'}`);
                        }
                      }}
                      disabled={healthAction.isPending}
                      className="text-xs text-gold hover:underline disabled:opacity-50"
                    >
                      Clear
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}