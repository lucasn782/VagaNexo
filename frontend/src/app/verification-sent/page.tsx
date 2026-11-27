"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ApiError, resendVerificationRequest } from "@/lib/api";

export default function VerificationSentPage() {
  const [email, setEmail] = useState("");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleResend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatusMessage(null);
    setSubmitting(true);
    try {
      const result = await resendVerificationRequest(email);
      setStatusMessage(result.detail);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Unable to resend verification email. Please try again.");
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
            Check your inbox
          </h1>
          <p className="text-sm text-muted-foreground">
            If your email is eligible for verification, a confirmation link has
            been sent.
          </p>
        </div>

        <form onSubmit={handleResend} className="space-y-3">
          <div className="space-y-1.5">
            <label
              htmlFor="resend-email"
              className="block text-sm font-medium text-foreground"
            >
              Need another link?
            </label>
            <input
              id="resend-email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:border-ring"
              placeholder="you@example.com"
            />
          </div>

          {statusMessage ? (
            <p role="status" className="text-sm text-foreground">
              {statusMessage}
            </p>
          ) : null}

          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}

          <Button
            type="submit"
            variant="outline"
            className="w-full"
            disabled={submitting}
          >
            {submitting ? "Sending..." : "Resend verification email"}
          </Button>
        </form>

        <p className="text-center text-xs text-muted-foreground">
          <Link href="/login" className="underline hover:text-foreground">
            Back to sign in
          </Link>
        </p>
      </section>
    </main>
  );
}
