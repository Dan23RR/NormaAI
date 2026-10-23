import { redirect } from 'next/navigation'

// /codex is the address printed in outreach emails. Vercel redirects it at
// the edge (vercel.json); this keeps the same behaviour in local dev.
export default function CodexRedirect() {
  redirect('/?codex=open#codex')
}
