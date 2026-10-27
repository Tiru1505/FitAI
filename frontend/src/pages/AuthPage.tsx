import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { CameraIcon, LogoMark, ShieldIcon, SparkIcon } from "../components/icons";
import { quoteOfTheDay } from "../components/quotes";
import { Alert, Button, Card, Field, Input } from "../components/ui";
import { credentialsSchema, fieldErrors, registerSchema, type FieldErrors } from "../lib/validation";

export default function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { token, login, register, guest } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [values, setValues] = useState({ email: "", password: "", confirm: "" });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [guestBusy, setGuestBusy] = useState(false);

  const continueAsGuest = async () => {
    setServerError(null);
    setGuestBusy(true);
    try {
      await guest();
      navigate("/", { replace: true });
    } catch (err) {
      setServerError(errorMessage(err));
    } finally {
      setGuestBusy(false);
    }
  };

  if (token) return <Navigate to="/" replace />;
  const isRegister = mode === "register";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setServerError(null);
    const parsed = isRegister ? registerSchema.safeParse(values) : credentialsSchema.safeParse(values);
    if (!parsed.success) {
      setErrors(fieldErrors(parsed.error));
      return;
    }
    setErrors({});
    setBusy(true);
    try {
      if (isRegister) {
        await register(values.email, values.password);
        navigate("/profile", { replace: true });
      } else {
        await login(values.email, values.password);
        navigate((location.state as { from?: string } | null)?.from ?? "/", { replace: true });
      }
    } catch (err) {
      setServerError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const set = (key: keyof typeof values) => (e: React.ChangeEvent<HTMLInputElement>) => setValues({ ...values, [key]: e.target.value });

  const quote = quoteOfTheDay();
  const highlights = [
    [<CameraIcon key="c" />, "Live form analysis", "Pose tracking runs in your browser — video never leaves this device"],
    [<SparkIcon key="s" />, "Plans that adapt", "Every change comes with the reason behind it"],
    [<ShieldIcon key="h" />, "Yours to delete", "One click removes everything the app has stored"],
  ] as const;

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10">
      {/* Soft drifting colour fields behind the form */}
      {/* Gym photograph, dimmed well below the text so contrast stays readable */}
      <img
        src="/images/gym-hero.jpg" alt="" aria-hidden
        className="pointer-events-none absolute inset-0 -z-20 h-full w-full scale-105 object-cover opacity-45"
      />
      {/* Scrims: strong behind the copy on the left, lighter on the right so the gym stays visible */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-r from-espresso-950 via-espresso-950/92 to-espresso-950/70" />
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-t from-espresso-950 via-transparent to-espresso-950/60" />
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="animate-drift absolute -left-32 -top-32 h-[30rem] w-[30rem] rounded-full bg-plum-600/30 blur-3xl" />
        <div className="animate-drift absolute -bottom-44 -right-28 h-[32rem] w-[32rem] rounded-full bg-ember-500/20 blur-3xl" style={{ animationDelay: "-7s" }} />
        <div className="animate-drift absolute left-1/3 top-1/4 h-80 w-80 rounded-full bg-mocha-500/25 blur-3xl" style={{ animationDelay: "-14s" }} />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_120%,rgba(20,14,10,0.6),transparent_60%)]" />
      </div>

      <div className="grid w-full max-w-4xl items-center gap-10 lg:grid-cols-[1.05fr_1fr]">
        <div className="hidden animate-fade-up lg:block">
          <LogoMark className="h-14 w-14" animated />
          <h1 className="mt-5 text-[2.6rem] font-semibold leading-[1.1] tracking-tight text-beige-100">
            Train with a coach<br />
            <span className="bg-gradient-to-r from-plum-300 via-plum-200 to-ember-300 bg-clip-text text-transparent">that actually watches.</span>
          </h1>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-beige-300">
            FitAI counts your repetitions, checks your technique as you move, and rewrites next week's plan from what
            you actually did.
          </p>
          <figure className="mt-5 max-w-md border-l-2 border-plum-400/60 pl-4">
            <blockquote className="text-sm italic text-beige-200">"{quote.text}"</blockquote>
            {quote.author && <figcaption className="mt-1 text-xs text-plum-300">— {quote.author}</figcaption>}
          </figure>
          <ul className="stagger mt-7 space-y-4">
            {highlights.map(([icon, title, body]) => (
              <li key={title} className="flex gap-3">
                <span className="mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-plum-500/15 text-plum-300 ring-1 ring-plum-400/20 [&>svg]:h-5 [&>svg]:w-5">
                  {icon}
                </span>
                <span>
                  <span className="block text-sm font-semibold text-beige-100">{title}</span>
                  <span className="block text-xs leading-relaxed text-beige-400">{body}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

      <div className="w-full animate-fade-up">
        <div className="mb-6 text-center lg:hidden">
          <LogoMark className="mx-auto h-12 w-12" animated />
          <h1 className="mt-3 text-2xl font-bold text-beige-100">FitAI</h1>
          <p className="text-sm text-beige-400">Adaptive workouts with real-time exercise analysis</p>
        </div>
        <Card title={isRegister ? "Create your account" : "Sign in"}>
          <form className="space-y-4" onSubmit={submit} noValidate>
            {serverError && <Alert tone="error">{serverError}</Alert>}
            <Field label="Email" error={errors.email}>
              <Input type="email" autoComplete="email" value={values.email} onChange={set("email")} />
            </Field>
            <Field label="Password" error={errors.password} hint={isRegister ? "8–72 characters with letters and digits" : undefined}>
              <Input type="password" autoComplete={isRegister ? "new-password" : "current-password"} value={values.password} onChange={set("password")} />
            </Field>
            {isRegister && (
              <Field label="Confirm password" error={errors.confirm}>
                <Input type="password" autoComplete="new-password" value={values.confirm} onChange={set("confirm")} />
              </Field>
            )}
            <Button type="submit" className="w-full" disabled={busy || guestBusy}>
              {busy ? "Please wait…" : isRegister ? "Create account" : "Sign in"}
            </Button>
          </form>

          <div className="my-5 flex items-center gap-3" aria-hidden>
            <span className="h-px flex-1 bg-gradient-to-r from-transparent via-beige-100/20 to-transparent" />
            <span className="text-[11px] uppercase tracking-[0.2em] text-beige-500">or</span>
            <span className="h-px flex-1 bg-gradient-to-r from-transparent via-beige-100/20 to-transparent" />
          </div>

          <div className="rounded-2xl border border-beige-100/10 bg-white/5 p-4">
            <p className="text-sm font-medium text-beige-100">Just want to look around?</p>
            <p className="mt-1 text-xs text-beige-400">
              A guest account comes with a bodyweight starter plan, so you can try a live session straight away.
              It is temporary: anything you record is deleted when you delete the data from Settings, and you
              cannot sign back into it once you sign out.
            </p>
            <Button variant="secondary" className="mt-3 w-full" disabled={busy || guestBusy} onClick={continueAsGuest}>
              {guestBusy ? "Setting up…" : "Continue as guest"}
            </Button>
          </div>
          <p className="mt-4 text-center text-sm text-beige-400">
            {isRegister ? (
              <>Already have an account? <Link className="text-plum-300 underline" to="/login">Sign in</Link></>
            ) : (
              <>New to FitAI? <Link className="text-plum-300 underline" to="/register">Create an account</Link></>
            )}
          </p>
        </Card>
        <p className="mt-4 text-center text-xs text-beige-500">
          Educational prototype. Not a substitute for professional medical or nutrition advice.
        </p>
      </div>
      </div>
    </div>
  );
}
