import Link from "next/link";
import { BookIcon, MicIcon, SparkIcon } from "@/components/icons";
import { ThemeToggle } from "@/components/theme-toggle";

const points = [
  {
    icon: <BookIcon className="size-4" />,
    title: "Upload once",
    body: "Your PDF is split by topic and turned into questions across five difficulty levels.",
  },
  {
    icon: <MicIcon className="size-4" />,
    title: "Answer out loud",
    body: "Graded on meaning, not keywords. Say it your way and it still counts.",
  },
  {
    icon: <SparkIcon className="size-4" />,
    title: "It adapts",
    body: "Get one right and it pushes harder. Struggle and it eases off.",
  },
];

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen">
      {/* Form side */}
      <div className="relative flex flex-1 items-center justify-center px-6 py-12">
        {/* Home link and theme toggle float over the form column so the form
            itself stays centred. */}
        <div className="absolute inset-x-0 top-0 flex items-center justify-between px-6 py-5">
          <Link
            href="/"
            className="flex items-center gap-2.5 rounded-lg transition-opacity hover:opacity-70 lg:invisible"
          >
            <span className="flex size-7 items-center justify-center rounded-lg bg-ink text-paper">
              <MicIcon className="size-3.5" />
            </span>
            <span className="font-serif text-[15px] text-ink">Study Coach</span>
          </Link>
          <ThemeToggle />
        </div>

        <div className="w-full max-w-[380px] animate-fade-up">{children}</div>
      </div>

      {/* Editorial side. Hidden below lg - on a phone it would just push the
          form off screen. */}
      <div className="hidden lg:flex lg:w-[46%] xl:w-[42%] flex-col justify-between bg-sunken border-l border-line p-12 xl:p-16">
        <Link
          href="/"
          className="flex w-fit items-center gap-2.5 transition-opacity hover:opacity-70"
        >
          <span className="flex size-7 items-center justify-center rounded-lg bg-ink text-paper">
            <MicIcon className="size-3.5" />
          </span>
          <span className="font-serif text-[15px] text-ink">Study Coach</span>
        </Link>

        <div className="max-w-md">
          <h2 className="font-serif text-[32px] xl:text-[38px] leading-[1.15] tracking-[-0.02em] text-ink">
            Reading your notes
            <br />
            <span className="text-ink-faint">is not the same as</span>
            <br />
            knowing them.
          </h2>
          <p className="mt-5 text-[15px] leading-relaxed text-ink-soft">
            Turn any set of notes into a spoken quiz that asks, listens, and
            adjusts to what you actually know.
          </p>

          <div className="mt-10 space-y-6">
            {points.map((p) => (
              <div key={p.title} className="flex gap-3.5">
                <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-surface border border-line text-ink-soft">
                  {p.icon}
                </div>
                <div>
                  <p className="text-sm font-medium text-ink">{p.title}</p>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-ink-faint">
                    {p.body}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="text-xs text-ink-ghost">
          Built with FastAPI, Supabase and Llama.
        </p>
      </div>
    </div>
  );
}
