'use client';

export default function ClientDate({ dateString }) {
  return <span suppressHydrationWarning>{new Date(dateString).toLocaleString()}</span>;
}
