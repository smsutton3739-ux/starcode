import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-md px-4 py-24 text-center">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="mt-2 text-slate-600 dark:text-slate-400">
        That page does not exist.
      </p>
      <Link href="/" className="btn-primary mt-6">
        Go to the homepage
      </Link>
    </div>
  );
}
