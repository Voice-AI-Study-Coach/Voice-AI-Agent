"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { MarketingNav } from "@/components/marketing-nav";
import { Button, Card, cx } from "@/components/ui";
import {
  ArrowRightIcon,
  BookIcon,
  CheckIcon,
  MicIcon,
  RepeatIcon,
  SparkIcon,
  TargetIcon,
  WaveIcon,
} from "@/components/icons";

const STEPS = [
  {
    n: "01",
    icon: <BookIcon className="size-4" />,
    title: "Upload your notes",
    body: "Drop in a PDF — lecture notes, a textbook chapter, a deck. It is split into topics and turned into questions across five difficulty levels, once.",
  },
  {
    n: "02",
    icon: <TargetIcon className="size-4" />,
    title: "Pick what to study",
    body: "Every topic shows how you did last time. Never attempted, worth revisiting, or already solid — so you spend your time where it counts.",
  },
  {
    n: "03",
    icon: <MicIcon className="size-4" />,
    title: "Answer out loud",
    body: "A question is read to you. You answer in your own words, the way you would in a viva or an interview — not by picking from four options.",
  },
  {
    n: "04",
    icon: <RepeatIcon className="size-4" />,
    title: "It adapts, then reports",
    body: "Get one right and the next is harder. Struggle and it eases off. At the end you get a per-topic breakdown, weakest first.",
  },
];

const BENEFITS = [
  {
    icon: <SparkIcon className="size-4" />,
    title: "Graded on meaning, not keywords",
    body: "Say it your way and it still counts. An LLM checks your answer against the key ideas, so a correct answer phrased differently is still correct.",
  },
  {
    icon: <WaveIcon className="size-4" />,
    title: "Speaking is the test",
    body: "Exams and interviews are spoken or written under pressure. Silently re-reading a page never trains that. Saying it out loud does.",
  },
  {
    icon: <TargetIcon className="size-4" />,
    title: "Difficulty that actually moves",
    body: "Your running score nudges the level up or down between questions, with a dead band so it drifts instead of flip-flopping every turn.",
  },
  {
    icon: <CheckIcon className="size-4" />,
    title: "Not knowing costs you nothing",
    body: "Say you do not know and it tells you the answer, kindly. If the mic does not catch you, that is a technical failure, not a wrong answer — it never counts against you.",
  },
  {
    icon: <RepeatIcon className="size-4" />,
    title: "Every topic starts fresh",
    body: "You might know one topic cold and the next not at all. The difficulty resets between topics, so you are never handed an expert question on material you have not read.",
  },
  {
    icon: <BookIcon className="size-4" />,
    title: "Upload once, come back forever",
    body: "The same PDF is recognised by its contents, not its filename. Re-upload it and you skip straight to the topics, with your history intact.",
  },
];

export default function HomePage() {
  const router = useRouter();
  // null = still checking; skip rendering the marketing page until we know,
  // so a logged-in user never sees a flash of it before being sent onward.
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null);

  useEffect(() => {
    api
      .me()
      .then(() => setLoggedIn(true))
      .catch(() => setLoggedIn(false));
  }, []);

  useEffect(() => {
    if (loggedIn) {
      router.replace("/library");
    }
  }, [loggedIn, router]);

  if (loggedIn === null || loggedIn) {
    return null;
  }

  const ctaHref = "/signup";

  return (
    <div className="min-h-screen bg-paper">
      <MarketingNav />

      {/* ---- Hero ---------------------------------------------------------- */}
      <section className="relative overflow-hidden">
        {/* A single soft wash behind the headline. Enough to stop the page
            reading as a plain document, subtle enough not to compete with it. */}
        <div
          aria-hidden
          className="pointer-events-none absolute left-1/2 top-[-18rem] size-[38rem] -translate-x-1/2 rounded-full opacity-[0.55] blur-3xl"
          style={{
            background:
              "radial-gradient(circle, var(--accent-soft) 0%, transparent 70%)",
          }}
        />

        <div className="relative mx-auto max-w-3xl px-6 pb-20 pt-20 text-center sm:pt-28">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-[12px] text-ink-soft animate-fade-in">
            <span className="size-1.5 rounded-full bg-accent" />
            Voice-first revision
          </span>

          <h1 className="mt-6 font-serif text-[40px] leading-[1.1] tracking-[-0.025em] text-ink sm:text-[56px] animate-fade-up">
            Reading your notes is not
            <br className="hidden sm:block" />{" "}
            <span className="text-ink-faint">the same as</span> knowing them.
          </h1>

          <p
            className="mx-auto mt-6 max-w-xl text-[17px] leading-relaxed text-ink-soft animate-fade-up"
            style={{ animationDelay: "60ms" }}
          >
            Study Coach turns any PDF into a spoken quiz that asks, listens, and
            adjusts to what you actually know — so you find your gaps before an
            exam does.
          </p>

          <div
            className="mt-9 flex flex-wrap items-center justify-center gap-3 animate-fade-up"
            style={{ animationDelay: "120ms" }}
          >
            <Link href={ctaHref}>
              <Button size="lg">
                Take a quiz
                <ArrowRightIcon className="size-4" />
              </Button>
            </Link>
            <a href="#how">
              <Button size="lg" variant="secondary">
                See how it works
              </Button>
            </a>
          </div>

          <p
            className="mt-4 text-[13px] text-ink-faint animate-fade-up"
            style={{ animationDelay: "160ms" }}
          >
            Free to use · Upload a PDF and start in about two minutes
          </p>
        </div>

        {/* Conversation preview - a still of the real thing, so the promise on
            this page is the product, not a stock illustration. */}
        <div className="mx-auto max-w-2xl px-6 pb-24">
          <Card
            className="overflow-hidden animate-fade-up"
            style={{ animationDelay: "200ms" }}
          >
            <div className="flex items-center gap-2 border-b border-line bg-sunken px-4 py-2.5">
              <span className="size-2 rounded-full bg-accent/70" />
              <span className="text-[12px] text-ink-faint">
                Lexical Analysis · Level 3
              </span>
            </div>
            <div className="space-y-4 p-5">
              <div>
                <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-ink-ghost">
                  Coach
                </p>
                <p className="mt-1.5 font-serif text-[19px] leading-snug text-ink">
                  What does the lexical analyser produce for each lexeme?
                </p>
              </div>
              <div>
                <p className="text-[11px] font-medium uppercase tracking-[0.1em] text-ink-ghost">
                  You
                </p>
                <p className="mt-1.5 text-[15px] leading-relaxed text-ink-soft">
                  It makes a token, something like a name and a value pointing
                  into the symbol table.
                </p>
              </div>
              <div className="rounded-xl bg-mastered-soft px-4 py-3">
                <p className="flex items-center gap-1.5 text-[12px] font-medium text-mastered">
                  <CheckIcon className="size-3" />
                  Correct
                </p>
                <p className="mt-1.5 text-[14px] leading-relaxed text-ink-soft">
                  That is right — a token of the form token-name and
                  attribute-value. Let us step it up.
                </p>
              </div>
            </div>
          </Card>
        </div>
      </section>

      {/* ---- What is it ---------------------------------------------------- */}
      <section className="border-y border-line bg-sunken">
        <div className="mx-auto grid max-w-5xl gap-10 px-6 py-20 md:grid-cols-[1fr_1.15fr] md:gap-16">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-ghost">
              What it is
            </p>
            <h2 className="mt-3 font-serif text-[30px] leading-tight tracking-[-0.02em] text-ink">
              A tutor for the notes you already have.
            </h2>
          </div>
          <div className="space-y-4 text-[16px] leading-relaxed text-ink-soft">
            <p>
              Most revision is passive. You read a chapter, it feels familiar,
              and familiarity gets mistaken for knowledge — until someone asks
              you a question and the words are not there.
            </p>
            <p>
              Study Coach closes that gap. It reads your material, works out
              what the topics are, writes questions on each of them, and then
              sits with you and asks. You answer aloud. It tells you what you
              got and what you missed.
            </p>
            <p className="text-ink">
              No question banks to buy. No flashcards to write. Your own notes,
              turned into the one thing that actually proves you know them:
              being asked.
            </p>
          </div>
        </div>
      </section>

      {/* ---- How it works --------------------------------------------------- */}
      <section id="how" className="scroll-mt-20">
        <div className="mx-auto max-w-5xl px-6 py-20">
          <div className="max-w-xl">
            <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-ghost">
              How it works
            </p>
            <h2 className="mt-3 font-serif text-[30px] leading-tight tracking-[-0.02em] text-ink">
              Four steps, then it is just a conversation.
            </h2>
          </div>

          <ol className="mt-12 grid gap-4 sm:grid-cols-2">
            {STEPS.map((step) => (
              <li key={step.n}>
                <Card className="h-full p-5">
                  <div className="flex items-center gap-3">
                    <span className="flex size-8 items-center justify-center rounded-lg bg-raised text-ink-soft">
                      {step.icon}
                    </span>
                    <span className="font-mono text-[12px] tracking-wider text-ink-ghost">
                      {step.n}
                    </span>
                  </div>
                  <h3 className="mt-4 font-serif text-[18px] text-ink">
                    {step.title}
                  </h3>
                  <p className="mt-2 text-[14px] leading-relaxed text-ink-faint">
                    {step.body}
                  </p>
                </Card>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ---- Why it works ---------------------------------------------------- */}
      <section id="why" className="scroll-mt-20 border-y border-line bg-sunken">
        <div className="mx-auto max-w-5xl px-6 py-20">
          <div className="max-w-xl">
            <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-ghost">
              Why it works
            </p>
            <h2 className="mt-3 font-serif text-[30px] leading-tight tracking-[-0.02em] text-ink">
              Built around how revision actually goes wrong.
            </h2>
          </div>

          <div className="mt-12 grid gap-x-10 gap-y-9 sm:grid-cols-2 lg:grid-cols-3">
            {BENEFITS.map((b) => (
              <div key={b.title}>
                <span className="flex size-8 items-center justify-center rounded-lg border border-line bg-surface text-ink-soft">
                  {b.icon}
                </span>
                <h3 className="mt-3.5 text-[15px] font-medium text-ink">
                  {b.title}
                </h3>
                <p className="mt-1.5 text-[14px] leading-relaxed text-ink-faint">
                  {b.body}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Closing CTA ----------------------------------------------------- */}
      <section className="mx-auto max-w-3xl px-6 py-24 text-center">
        <h2 className="font-serif text-[32px] leading-tight tracking-[-0.02em] text-ink sm:text-[38px]">
          Find out what you actually know.
        </h2>
        <p className="mx-auto mt-4 max-w-md text-[16px] leading-relaxed text-ink-soft">
          Upload one PDF and take a quiz on it. It takes about two minutes to
          find your first gap.
        </p>
        <div className="mt-8 flex justify-center">
          <Link href={ctaHref}>
            <Button size="lg">
              Take a quiz
              <ArrowRightIcon className="size-4" />
            </Button>
          </Link>
        </div>
      </section>

      {/* ---- Footer ---------------------------------------------------------- */}
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4 px-6 py-8">
          <div className="flex items-center gap-2.5">
            <span className="flex size-6 items-center justify-center rounded-md bg-ink text-paper">
              <MicIcon className="size-3" />
            </span>
            <span className="font-serif text-[14px] text-ink">Study Coach</span>
          </div>
          <p className="text-[12px] text-ink-ghost">
            Built with FastAPI, Supabase, Llama and Gemini.
          </p>
        </div>
      </footer>
    </div>
  );
}
