"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

function LoginForm() {
  const q = useSearchParams();
  const failed = q.get("error") === "1";
  const next = q.get("next") ?? "/";
  return (
    <form method="post" action="/auth/login" className="card w-full max-w-sm p-6">
      <div className="display text-[22px] font-medium leading-tight">
        oalgo<span className="text-accent">2</span>
      </div>
      <p className="mt-1 text-[12.5px] text-dim">Sign in to your research observatory.</p>
      <input type="hidden" name="next" value={next} />
      <label htmlFor="password" className="mt-5 block text-[12px] text-dim">
        Password
      </label>
      <input id="password" name="password" type="password" required autoFocus autoComplete="current-password" className="input mt-1 w-full py-2 text-[13px]" />
      {failed && (
        <p className="mt-2 text-[12px] text-down" role="alert">
          That password is not right. Try again.
        </p>
      )}
      <button type="submit" className="btn btn-primary mt-4 w-full py-2 text-[13px]">
        Sign in
      </button>
      <p className="note mt-4">Research and tracking only. This platform cannot place orders.</p>
    </form>
  );
}

export default function Login() {
  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <Suspense>
        <LoginForm />
      </Suspense>
    </div>
  );
}
