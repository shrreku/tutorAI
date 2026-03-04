import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Home, Plus, Sparkles, SlidersHorizontal, CreditCard, LogOut, NotebookPen } from 'lucide-react';
import { cn } from '../../lib/utils';
import { useAuth } from '../../hooks/useAuth';

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const notebooksEnabled = import.meta.env.VITE_FEATURE_NOTEBOOKS_ENABLED !== 'false';

  const navItems = [
    { href: '/', label: 'Studio', icon: Home },
    ...(notebooksEnabled ? [{ href: '/notebooks', label: 'Notebooks', icon: NotebookPen }] : []),
    { href: '/billing', label: 'Billing', icon: CreditCard },
    { href: '/settings', label: 'Settings', icon: SlidersHorizontal },
  ];

  const isActive = (href: string) => {
    if (href === '/') return location.pathname === '/';
    return location.pathname.startsWith(href);
  };

  const handleLogout = () => {
    logout();
    navigate('/landing', { replace: true });
  };

  const initials = (user?.display_name || user?.email || 'S')
    .split(' ')
    .map(w => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <aside className="w-72 flex flex-col bg-sidebar border-r border-border/50 grain">
      <div className="p-6 pb-4">
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center group-hover:bg-gold/20 transition-colors">
            <Sparkles className="w-4 h-4 text-gold" />
          </div>
          <div>
            <h1 className="font-display text-lg font-semibold text-foreground tracking-tight leading-none">
              StudyAgent
            </h1>
            <p className="text-[10px] uppercase tracking-[0.2em] text-sidebar-foreground/50 mt-0.5">
              Learning Studio
            </p>
          </div>
        </Link>
      </div>

      <div className="px-6 mb-4">
        <p className="text-xs text-sidebar-foreground/70 leading-relaxed">
          Turn any textbook into conversations.
        </p>
      </div>

      <div className="px-3 mb-4">
        <Link
          to="/notebooks/new"
          className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-lg bg-gold/10 border border-gold/20 text-gold hover:bg-gold/20 hover:border-gold/30 transition-all text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          New Notebook
        </Link>
      </div>

      <nav className="flex-1 px-3 space-y-1">
        {navItems.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            to={href}
            className={cn(
              'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150',
              isActive(href)
                ? 'bg-gold/10 text-gold border border-gold/15'
                : 'text-sidebar-foreground hover:text-foreground hover:bg-white/[0.04] border border-transparent'
            )}
          >
            <Icon className={cn('w-[18px] h-[18px]', isActive(href) ? 'text-gold' : 'text-sidebar-foreground')} />
            {label}
          </Link>
        ))}
      </nav>

      <div className="p-4 mt-auto border-t border-border/30">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-gold/10 border border-gold/20 flex items-center justify-center">
            <span className="text-xs font-medium text-gold">{initials}</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-foreground truncate">
              {user?.display_name || 'Student'}
            </p>
            <p className="text-[11px] text-sidebar-foreground truncate">
              {user?.email || 'In session'}
            </p>
          </div>
          <button
            onClick={handleLogout}
            title="Sign out"
            className="shrink-0 p-1.5 rounded-md text-sidebar-foreground/50 hover:text-foreground hover:bg-white/[0.06] transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
