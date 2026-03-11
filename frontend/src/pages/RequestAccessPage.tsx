import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, MailCheck, Sparkles } from 'lucide-react';
import { apiGetAuthConfig, useAuth } from '../hooks/useAuth';

export default function RequestAccessPage() {
  const { requestAccess } = useAuth();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [promoCode, setPromoCode] = useState('');
  const [alphaEnabled, setAlphaEnabled] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void apiGetAuthConfig()
      .then((config) => {
        if (!cancelled) {
          setAlphaEnabled(config.alpha_access_enabled);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAlphaEnabled(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      const response = await requestAccess({
        email,
        display_name: displayName,
        promo_code: promoCode.trim() || undefined,
      });
      setMessage(response.message);
    } catch (requestError: any) {
      setError(requestError?.message || 'Could not submit your access request.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-background relative overflow-hidden">
      <div
        className="pointer-events-none fixed inset-0 opacity-40"
        style={{
          backgroundImage:
            'radial-gradient(ellipse 55% 45% at 70% 25%, rgba(212,160,60,0.1), transparent),' +
            'radial-gradient(ellipse 50% 40% at 25% 75%, rgba(212,160,60,0.07), transparent)',
        }}
      />
      <div className="pointer-events-none fixed inset-0 grain" />

      <div className="flex-1 flex items-center justify-center px-6 py-12 relative z-10">
        <div className="w-full max-w-md rounded-2xl border border-border bg-card/70 p-8 backdrop-blur-sm">
          <Link to="/landing" className="inline-flex items-center gap-2.5 mb-8 group">
            <div className="w-8 h-8 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center group-hover:bg-gold/20 transition-colors">
              <Sparkles className="w-4 h-4 text-gold" />
            </div>
            <span className="font-display text-lg font-semibold text-foreground tracking-tight">StudyAgent</span>
          </Link>

          <h1 className="font-display text-3xl font-semibold text-foreground tracking-tight mb-2">
            {alphaEnabled ? 'Request access' : 'Join StudyAgent'}
          </h1>
          <p className="text-sm text-muted-foreground mb-8">
            {alphaEnabled
              ? 'The landing page is public. Account creation is currently approval-based during alpha.'
              : 'Open registration is enabled right now. You can create an account directly.'}
          </p>

          {message && (
            <div className="mb-6 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200 flex items-start gap-2">
              <MailCheck className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{message}</span>
            </div>
          )}
          {error && (
            <div className="mb-6 rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="displayName" className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                Name
              </label>
              <input
                id="displayName"
                type="text"
                required
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                className="w-full rounded-lg border border-border bg-card/60 px-4 py-3 text-sm text-foreground"
                placeholder="Alex Chen"
              />
            </div>

            <div>
              <label htmlFor="email" className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="w-full rounded-lg border border-border bg-card/60 px-4 py-3 text-sm text-foreground"
                placeholder="you@university.edu"
              />
            </div>

            <div>
              <label htmlFor="promoCode" className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                Promo code (optional)
              </label>
              <input
                id="promoCode"
                type="text"
                value={promoCode}
                onChange={(event) => setPromoCode(event.target.value)}
                className="w-full rounded-lg border border-border bg-card/60 px-4 py-3 text-sm text-foreground"
                placeholder="EARLYACCESS2026"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-gold text-primary-foreground font-semibold text-sm py-3 shadow-md shadow-gold/20 disabled:opacity-50"
            >
              {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Submitting…</> : 'Request access'}
            </button>
          </form>

          <p className="mt-8 text-center text-sm text-muted-foreground">
            {alphaEnabled ? (
              <>
                Already approved?{' '}
                <Link to="/register" className="text-gold hover:underline font-medium">Create your account</Link>
              </>
            ) : (
              <>
                Registration is open.{' '}
                <Link to="/register" className="text-gold hover:underline font-medium">Go to sign up</Link>
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}