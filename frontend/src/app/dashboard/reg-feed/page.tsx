'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

/** Redirect /dashboard/reg-feed → /dashboard/regulatory-feed */
export default function RegFeedRedirect() {
  const router = useRouter()
  useEffect(() => {
    router.replace('/dashboard/regulatory-feed')
  }, [router])
  return null
}
