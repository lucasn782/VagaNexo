"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/auth/auth-provider";
import {
  ApiError,
  type CandidateProfileSummary,
  fetchOwnedProfiles,
} from "@/lib/api";

export default function Home() {
  const { user, loading, logout, refreshSession } = useAuth();
  const [profiles, setProfiles] = useState<CandidateProfileSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) {
      return;
    }
    let active = true;
    fetchOwnedProfiles()
      .then((items) => {
        if (active) {
          setProfiles(items);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401) {
          void refreshSession();
          return;
        }
        setError("Failed to load profiles.");
      });
    return () => {
      active = false;
    };
  }, [user, refreshSession]);

  if (loading || !user) {
    return (
      <main className="flex min-h-screen items-center justify-center p-6">
        <p className="text-sm text-muted-foreground">Checking session...</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <header className="flex items-center justify-between border-b border-border pb-4">
        <div>
          <h1 className="text-xl font-semibold">VagaNexo AI</h1>
          <p className="text-sm text-muted-foreground">
            Signed in as {user.email}
          </p>
        </div>
        <Button variant="outline" onClick={() => void logout()}>
          Sign out
        </Button>
      </header>

      <section className="space-y-3">
        <h2 className="text-base font-medium">Your Profiles</h2>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        {profiles.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No profiles assigned to this account yet.
          </p>
        ) : (
          <ul className="space-y-2">
            {profiles.map((profile) => (
              <li
                key={profile.id}
                className="rounded-md border border-border bg-card p-3"
              >
                <p className="font-medium">{profile.full_name}</p>
                {profile.professional_headline ? (
                  <p className="text-sm text-muted-foreground">
                    {profile.professional_headline}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
