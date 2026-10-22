import { useState } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";

import { errorMessage } from "../api/client";
import { useMe } from "../api/hooks";
import { useAuth } from "../auth/AuthContext";
import { LogoMark } from "./icons";
import { Alert, Button, Spinner } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/plan", label: "Workout plan" },
  { to: "/session", label: "Live session" },
  { to: "/progress", label: "Progress" },
  { to: "/nutrition", label: "Nutrition" },
  { to: "/settings", label: "Settings & privacy" },
];

export function ProtectedLayout() {
  const { token, logout } = useAuth();
  const me = useMe(!!token);
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (me.isLoading) return <div className="p-8"><Spinner /></div>;
  if (me.isError) {
    return (
      <div className="mx-auto max-w-lg p-8">
        <Alert tone="error" title="Could not load your account">{errorMessage(me.error)}</Alert>
        <Button className="mt-4" variant="secondary" onClick={() => me.refetch()}>Retry</Button>
      </div>
    );
  }
  const needsProfile = !me.data?.profile && location.pathname !== "/profile" && location.pathname !== "/settings";
  if (needsProfile) return <Navigate to="/profile" replace />;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-beige-100/10 bg-espresso-950/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-2.5 text-lg font-bold tracking-tight text-beige-100 transition-opacity hover:opacity-80">
            <LogoMark className="h-8 w-8" />
            FitAI
          </NavLink>
          <nav className="hidden gap-1 lg:flex" aria-label="Main">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `rounded-xl px-3 py-2 text-sm transition-all duration-200 ${
                    isActive ? "bg-plum-500/12 font-medium text-plum-300 shadow-sm" : "text-beige-300 hover:bg-white/5 hover:text-plum-200"
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <span className="hidden text-sm text-beige-400 sm:inline">{me.data?.profile?.display_name || me.data?.email}</span>
            <Button variant="ghost" onClick={logout}>Sign out</Button>
            <Button variant="secondary" className="lg:hidden" aria-expanded={menuOpen} onClick={() => setMenuOpen((o) => !o)}>
              Menu
            </Button>
          </div>
        </div>
        {menuOpen && (
          <nav className="grid gap-1 border-t border-beige-100/12 px-4 py-2 lg:hidden" aria-label="Mobile">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} onClick={() => setMenuOpen(false)} className="rounded-lg px-3 py-2 text-sm text-beige-200 hover:bg-white/5">
                {n.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>
      {me.data?.is_guest && (
        <div className="border-b border-ember-400/25 bg-ember-500/10 backdrop-blur-sm">
          <p className="mx-auto max-w-6xl px-4 py-2 text-sm text-ember-200">
            You are signed in as a <strong>guest</strong>. This account is temporary — you cannot sign back into it
            after signing out. <NavLink to="/register" className="underline">Create an account</NavLink> to keep your
            progress.
          </p>
        </div>
      )}
      <main key={location.pathname} className="mx-auto max-w-6xl animate-fade-up px-4 py-6">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs text-beige-500">
        FitAI is an educational prototype and does not provide medical advice.
      </footer>
    </div>
  );
}
