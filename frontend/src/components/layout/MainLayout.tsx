import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export function MainLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    typeof window !== 'undefined' && localStorage.getItem('sidebar-collapsed') === 'true'
  );

  const toggleSidebar = () => {
    setSidebarCollapsed(prev => {
      const next = !prev;
      localStorage.setItem('sidebar-collapsed', String(next));
      return next;
    });
  };

  return (
    <div className="flex h-screen bg-background relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 opacity-40"
        style={{
          backgroundImage:
            'radial-gradient(circle at 12% 8%, rgba(212,160,60,0.09), transparent 38%), radial-gradient(circle at 84% 18%, rgba(212,160,60,0.08), transparent 32%), radial-gradient(circle at 40% 86%, rgba(212,160,60,0.06), transparent 28%)',
        }}
      />
      <Sidebar collapsed={sidebarCollapsed} onToggle={toggleSidebar} />
      <main className="flex-1 overflow-auto relative z-10">
        <div className="h-full">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
