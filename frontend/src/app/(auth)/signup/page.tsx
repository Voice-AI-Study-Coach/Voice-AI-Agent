"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button, ErrorNote, Input } from "@/components/ui";

export default function SignupPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.signup(name, email, password);
      // Signup does not set a cookie, so log in immediately rather than
      // sending the user to a form they just filled out.
      await api.login(email, password);
      window.location.href = "/library";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create account");
      setLoading(false);
    }
  }

  return (
    <div>
      <h1 className="font-serif text-[28px] tracking-[-0.02em] text-ink">
        Create your account
      </h1>
      <p className="mt-1.5 text-sm text-ink-faint">
        Upload a PDF and start quizzing in a couple of minutes.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <Input
          label="Name"
          name="name"
          autoComplete="name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Shiva"
        />
        <Input
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
        />
        <Input
          label="Password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 8 characters"
          hint="Use something you do not use elsewhere."
        />

        <ErrorNote>{error}</ErrorNote>

        <Button type="submit" size="lg" loading={loading} className="w-full">
          Create account
        </Button>
      </form>

      <p className="mt-8 text-center text-sm text-ink-faint">
        Already have an account?{" "}
        <Link
          href="/login"
          className="font-medium text-ink underline decoration-line-strong underline-offset-4 transition-colors hover:decoration-ink"
        >
          Sign in
        </Link>
      </p>
    </div>
  );
}
