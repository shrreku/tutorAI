import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Home, Plus, Sparkles, SlidersHorizontal, CreditCard, LogOut,
  NotebookPen, Shield, FolderOpen, PanelLeftClose, PanelLeftOpen,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { useAuth } from '../../hooks/useAuth';

type SidebarProps = {
  collapsed: boolean;
  onToggle: () => void;
};

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const notebooksEnabled = import.meta.env.VITE_FEATURE_NOTEBOOKS_ENABLED !== 'false';

  const navItems = [
    { href: '/', label: 'Studio', icon: Home },
    ...(notebooksEnabled ? [{ href: '/notebooks', label: 'Notebooks', icon: NotebookPen }] : []),
    { href: '/resources', label: 'Resources', icon: FolderOpen },
    { href: '/billing', label: 'Billing', icon: CreditCard },
    ...(user?.is_admin ? [{ href: '/admin', label: 'Admin', icon: Shield }] : []),
    { href: '/settings', label: 'Settings', icon: SlidersHorizontal },
  ];

  const isActive = (href: string) => {
    if (href === '/') return location.pathname === '/';
    if (href === '/resources') return location.pathname === '/resources';
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
    <aside className={cn(
      'flex flex-col bg-sidebar border-r border-border/50 transition-all duration-300 ease-in-out shrink-0 overflow-hidden',
      collapsed ? 'w-[72px]' : 'w-[260px]'
    )}>
      {/* Logo + toggle */}
      <div className={cn('flex items-center p-4 pb-3', collapsed ? 'justify-center' : 'justify-between')}>
        <Link to="/" className="flex items-center gap-2.5 group shrink-0">
          <div className="w-8 h-8 rounded-lg bg-gold/10 border border-gold/20 flex items-center justify-center group-hover:bg-gold/20 transition-colors shrink-0">
            <Sparkles className="w-4 h-4 text-gold" />
          </div>
          {!collapsed && (
            <div className="overflow-hidden">
              <h1 className="font-display text-lg font-semibold text-foreground tracking-tight leading-none whitespace-nowrap">
                StudyAgent
              </h1>
              <p className="text-[10px] uppercase tracking-[0.2em] text-sidebar-foreground/50 mt-0.5 whitespace-nowrap">
                Learning Studio
              </p>
            </div>
          )}
        </Link>
        {!collapsed && (
          <button
            onClick={onToggle}
            className="p-1.5 rounded-md text-sidebar-foreground/40 hover:text-sidebar-foreground hover:bg-white/[0.08] transition-colors shrink-0"
            title="Collapse sidebar"
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Tagline */}
      {!collapsed && (
        <div className="px-4 mb-4">
          <p className="text-xs text-sidebar-foreground/70 leading-relaxed">
            Turn any textbook into conversations.
          </p>
        </div>
      )}

      {/* New Notebook */}
      <div className={cn('mb-4', collapsed ? 'px-2.5' : 'px-3')}>
        <Link
          to="/notebooks/new"
          className={cn(
            'flex items-center justify-center gap-2 w-full rounded-lg bg-gold/10 border border-gold/20 text-gold hover:bg-gold/20 hover:border-gold/30 transition-all text-sm font-medium',
            collapsed ? 'px-2 py-2.5' : 'px-4 py-2.5'
          )}
          title={collapsed ? 'New Notebook' : undefined}
        >
          <Plus className="w-4 h-4 shrink-0" />
          {!collapsed && <span className="whitespace-nowrap">New Notebook</span>}
        </Link>
      </div>

      {/* Expand toggle (collapsed mode) */}
      {collapsed && (
        <div className="px-2.5 mb-2">
          <button
            onClick={onToggle}
            className="w-full flex items-center justify-center p-2 rounded-md text-sidebar-foreground/40 hover:text-sidebar-foreground hover:bg-white/[0.08] transition-colors"
            title="Expand sidebar"
          >
            <PanelLeftOpen className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Navigation */}
      <nav className={cn('flex-1 space-y-1', collapsed ? 'px-2.5' : 'px-3')}>
        {navItems.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            to={href}
            title={collapsed ? label : undefined}
            className={cn(
              'flex items-center gap-3 rounded-lg text-sm font-medium transition-all duration-150',
              collapsed ? 'justify-center px-2 py-2.5' : 'px-3 py-2.5',
              isActive(href)
                ? 'bg-gold/10 text-gold border border-gold/15'
                : 'text-sidebar-foreground hover:text-sidebar-foreground hover:bg-white/[0.06] border border-transparent'
            )}
          >
            <Icon className={cn('w-[18px] h-[18px] shrink-0', isActive(href) ? 'text-gold' : 'text-sidebar-foreground')} />
            {!collapsed && <span className="whitespace-nowrap">{label}</span>}
          </Link>
        ))}
      </nav>

      {/* User */}
      <div className={cn('mt-auto border-t border-border/30', collapsed ? 'p-2.5' : 'p-4')}>
        <div className={cn('flex items-center', collapsed ? 'justify-center' : 'gap-3')}>
          <div className="w-8 h-8 rounded-full bg-gold/10 border border-gold/20 flex items-center justify-center shrink-0">
            <span className="text-xs font-medium text-gold">{initials}</span>
          </div>
          {!collapsed && (
            <>
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
                className="shrink-0 p-1.5 rounded-md text-sidebar-foreground/50 hover:text-sidebar-foreground hover:bg-white/[0.08] transition-colors"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}
