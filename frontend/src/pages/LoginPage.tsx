import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Sparkles, Eye, EyeOff, Loader2 } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login({ email, password });
      navigate('/', { replace: true });
    } catch (err: any) {
      setError(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-background relative overflow-hidden">
      {/* Ambient glow */}
      <div
        className="pointer-events-none fixed inset-0 opacity-40"
        style={{
          backgroundImage:
            'radial-gradient(ellipse 60% 50% at 30% 30%, rgba(212,160,60,0.1), transparent),' +
            'radial-gradient(ellipse 50% 40% at 70% 70%, rgba(212,160,60,0.07), transparent)',
        }}
      />
      <div className="pointer-events-none fixed inset-0 grain" />

      {/* Left decorative panel (hidden on small screens) */}
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
            Welcome<br />back.
          </h2>
          <p className="text-muted-foreground leading-relaxed">
            Pick up exactly where you left off — your sessions, mastery progress,
            and uploaded materials are waiting.
          </p>
        </div>

        <p className="text-xs text-muted-foreground/50">
          &copy; {new Date().getFullYear()} StudyAgent
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
            Sign in
          </h1>
          <p className="text-sm text-muted-foreground mb-8">
            Enter your credentials to access your learning studio.
          </p>

          {error && (
            <div className="mb-6 rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive animate-fade-in">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoFocus
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
                  autoComplete="current-password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full rounded-lg border border-border bg-card/60 px-4 py-3 pr-11 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-gold/40 focus:border-gold/30 transition-all"
                  placeholder="••••••••"
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
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-gold text-primary-foreground font-semibold text-sm py-3 shadow-md shadow-gold/20 hover:brightness-110 hover:shadow-lg hover:shadow-gold/30 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Signing in…
                </>
              ) : (
                'Sign in'
              )}
            </button>
          </form>

          <p className="mt-8 text-center text-sm text-muted-foreground">
            Don&apos;t have an account?{' '}
            <Link to="/register" className="text-gold hover:underline font-medium">
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
