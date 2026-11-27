"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ApiError, verifyEmailRequest } from "@/lib/api";

export default function VerifyEmailPage() {
  // Token kept exclusively in component memory and scrubbed from the URL bar
  // on mount; never persisted to localStorage/sessionStorage or consumed on GET.
  const [token, setToken] = useState<string | null>(null);
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const extracted = params.get("token");
    if (extracted) {
      window.history.replaceState({}, "", "/verify-email");
      window.setTimeout(() => setToken(extracted), 0);
    }
  }, []);

  async function handleConfirm() {
    if (!token) {
      setError("Verification token is missing or invalid.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await verifyEmailRequest(token);
      setVerified(true);
      setToken(null);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Unable to verify email address. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <section className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-xs space-y-5">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold text-card-foreground">
            Email verification
          </h1>
          <p className="text-sm text-muted-foreground">
            {verified
              ? "Your email address has been verified. You can now sign in."
              : "Confirm below to activate your VagaNexo AI account."}
          </p>
        </div>

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        {verified ? (
          <Link href="/login" className={cn(buttonVariants(), "w-full")}>
            Continue to sign in
          </Link>
        ) : token ? (
          <Button
            type="button"
            className="w-full"
            disabled={submitting}
            onClick={() => void handleConfirm()}
          >
            {submitting ? "Verifying..." : "Confirm email address"}
          </Button>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              No verification token was provided. Request a new link if needed.
            </p>
            <Link
              href="/verification-sent"
              className={cn(buttonVariants({ variant: "outline" }), "w-full")}
            >
              Resend verification email
            </Link>
          </div>
        )}
      </section>
    </main>
  );
}
