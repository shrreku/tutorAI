import { Link, useLocation } from 'react-router-dom';
import { Home, BookOpen, MessageSquare, Plus, Sparkles } from 'lucide-react';
import { cn } from '../../lib/utils';

const navItems = [
  { href: '/', label: 'Home', icon: Home },
  { href: '/resources', label: 'Resources', icon: BookOpen },
  { href: '/sessions', label: 'Sessions', icon: MessageSquare },
];

export function Sidebar() {
  const location = useLocation();

  const isActive = (href: string) => {
    if (href === '/') return location.pathname === '/';
    return location.pathname.startsWith(href);
  };

  return (
    <aside className="w-64 flex flex-col bg-sidebar border-r border-border/50 grain">
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
              AI Tutor
            </p>
          </div>
        </Link>
      </div>

      <div className="px-3 mb-4">
        <Link
          to="/sessions/new"
          className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-lg bg-gold/10 border border-gold/20 text-gold hover:bg-gold/20 hover:border-gold/30 transition-all text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          New Session
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
            <span className="text-xs font-medium text-gold">S</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-foreground truncate">Student</p>
            <p className="text-[11px] text-sidebar-foreground truncate">Active</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
