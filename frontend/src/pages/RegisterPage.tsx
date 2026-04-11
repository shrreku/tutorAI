import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Sparkles, Eye, EyeOff, Loader2, ShieldCheck } from 'lucide-react';
import { apiGetAuthConfig, useAuth } from '../hooks/useAuth';

export default function RegisterPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { register } = useAuth();

  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [consentTraining, setConsentTraining] = useState(false);
  const [consentPersonalization, setConsentPersonalization] = useState(false);
  const [accessCode, setAccessCode] = useState(searchParams.get('access') ?? searchParams.get('promo') ?? '');
  const inviteToken = searchParams.get('invite') ?? '';
  const [alphaEnabled, setAlphaEnabled] = useState(false);
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

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setLoading(true);
    try {
      await register({
        email,
        password,
        display_name: displayName,
        consent_training: consentTraining,
        consent_personalization: consentPersonalization,
        invite_token: inviteToken.trim() || undefined,
        access_code: accessCode.trim() || undefined,
      });
      navigate('/', { replace: true });
    } catch (err: any) {
      setError(err.message || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-background">

      {/* Left decorative panel */}
      <div className="hidden lg:flex flex-col justify-between w-[45%] relative z-10 px-12 py-10">
        <Link to="/landing" className="flex items-center gap-2.5 group">
          <div className="w-9 h-9 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center group-hover:bg-gold/20 transition-colors">
            <Sparkles className="w-4.5 h-4.5 text-gold" />
          </div>
          <span className="font-display text-xl font-semibold text-foreground tracking-tight">
            StudyAgent
          </span>
        </Link>

        <div className="max-w-md">
          <h2 className="font-display text-4xl font-semibold text-foreground tracking-tight leading-[1.12] mb-4">
            Start your<br />
            <span className="italic text-gold">learning journey.</span>
          </h2>
          <p className="text-muted-foreground leading-relaxed mb-6">
            Create an account in seconds — upload your first PDF and have a
            grounded tutoring conversation within minutes.
          </p>
          <div className="flex items-start gap-3 p-4 rounded-lg border border-border bg-card/30">
            <ShieldCheck className="w-5 h-5 text-gold mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-foreground mb-1">Consent is captured here</p>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Research and personalization consent are set during account creation, not later in Settings.
                Access-code welcome credits are only issued when research consent is enabled.
              </p>
            </div>
          </div>
        </div>

        <p className="text-xs text-muted-foreground/50">
          &copy; {new Date().getFullYear()} StudyAgent &middot; Student Research Project
        </p>
      </div>

      {/* Right form panel */}
      <div className="flex-1 flex items-center justify-center px-6 py-12 relative z-10">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2.5 mb-10">
            <Link to="/landing" className="flex items-center gap-2.5 group">
              <div className="w-8 h-8 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center group-hover:bg-gold/20 transition-colors">
                <Sparkles className="w-4 h-4 text-gold" />
              </div>
              <span className="font-display text-lg font-semibold text-foreground tracking-tight">
                StudyAgent
              </span>
            </Link>
          </div>

          <h1 className="font-display text-3xl font-semibold text-foreground tracking-tight mb-2">
            Create account
          </h1>
          <p className="text-sm text-muted-foreground mb-8">
            {alphaEnabled
              ? inviteToken
                ? 'Create your account with the invite already attached to this link.'
                : 'Create your account with your access code.'
              : 'Set up your learning studio in a few seconds.'}
          </p>

          {error && (
            <div className="mb-6 rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive animate-fade-in">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Display Name */}
            <div>
              <label htmlFor="displayName" className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                Name
              </label>
              <input
                id="displayName"
                type="text"
                required
                autoFocus
                autoComplete="name"
                value={displayName}
                onChange={e => setDisplayName(e.target.value)}
                className="w-full rounded-lg border border-border bg-card/60 px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-gold/40 focus:border-gold/30 transition-all"
                placeholder="Alex Chen"
              />
            </div>

            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full rounded-lg border border-border bg-card/60 px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-gold/40 focus:border-gold/30 transition-all"
                placeholder="you@university.edu"
              />
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPw ? 'text' : 'password'}
                  required
                  minLength={8}
                  autoComplete="new-password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full rounded-lg border border-border bg-card/60 px-4 py-3 pr-11 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-gold/40 focus:border-gold/30 transition-all"
                  placeholder="Min. 8 characters"
                />
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => setShowPw(p => !p)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-muted-foreground transition-colors"
                >
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <p className="mt-1 text-xs text-muted-foreground/60">At least 8 characters</p>
            </div>

            {alphaEnabled && !inviteToken && (
              <div>
                <label htmlFor="accessCode" className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                  Access code
                </label>
                <input
                  id="accessCode"
                  type="text"
                  value={accessCode}
                  onChange={e => setAccessCode(e.target.value)}
                  className="w-full rounded-lg border border-border bg-card/60 px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground/50"
                  placeholder="Enter your access code"
                />
                <p className="mt-1 text-xs text-muted-foreground/70">
                  If you use an access code, free welcome credits are granted only when research consent is checked.
                </p>
              </div>
            )}

            <div className="rounded-lg border border-border bg-card/40 p-4 space-y-4">
              <label className="flex items-start gap-3 cursor-pointer group">
                <div className="relative mt-0.5">
                  <input
                    type="checkbox"
                    checked={consentTraining}
                    onChange={e => setConsentTraining(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-5 h-5 rounded border-2 border-border bg-card peer-checked:border-gold peer-checked:bg-gold/20 transition-all flex items-center justify-center">
                    {consentTraining && (
                      <svg className="w-3 h-3 text-gold" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </div>
                </div>
                <div>
                  <span className="text-sm font-medium text-foreground block mb-1">
                    Contribute to research
                  </span>
                  <span className="text-xs text-muted-foreground leading-relaxed block">
                    I agree to let my <strong>anonymised</strong> tutoring interactions be used for
                    academic research on AI tutoring quality. No personally identifiable information
                    is included.
                  </span>
                </div>
              </label>

              <label className="flex items-start gap-3 cursor-pointer group">
                <div className="relative mt-0.5">
                  <input
                    type="checkbox"
                    checked={consentPersonalization}
                    onChange={e => setConsentPersonalization(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-5 h-5 rounded border-2 border-border bg-card peer-checked:border-gold peer-checked:bg-gold/20 transition-all flex items-center justify-center">
                    {consentPersonalization && (
                      <svg className="w-3 h-3 text-gold" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </div>
                </div>
                <div>
                  <span className="text-sm font-medium text-foreground block mb-1">
                    Allow personalization
                  </span>
                  <span className="text-xs text-muted-foreground leading-relaxed block">
                    Let StudyAgent adapt pacing, depth, hints, and examples based on your notebook and session preferences.
                  </span>
                </div>
              </label>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-gold text-primary-foreground font-semibold text-sm py-3 hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Creating account…
                </>
              ) : (
                'Create account'
              )}
            </button>
          </form>

          <p className="mt-8 text-center text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link to="/login" className="text-gold hover:underline font-medium">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
