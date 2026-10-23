'use client'

import { Component, type ReactNode } from 'react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/Button'

interface Props {
  children: ReactNode
  fallback?: ReactNode
  /** The words of the default fallback, resolved by the wrapper below. */
  texts: { title: string; body: (message: string) => string; unexpected: string; retry: string }
}

interface State {
  hasError: boolean
  error: Error | null
}

class ErrorBoundaryInner extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback
      const { texts } = this.props
      return (
        <div className="flex min-h-[400px] items-center justify-center p-8">
          <div className="max-w-lg rounded-lg border border-bad/30 bg-surface p-8 text-center">
            <h2 className="text-h3">{texts.title}</h2>
            <p className="mt-2 text-body text-ink-2">{texts.body(this.state.error?.message || texts.unexpected)}</p>
            <Button className="mt-6" onClick={() => this.setState({ hasError: false, error: null })}>
              {texts.retry}
            </Button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

/** Class components cannot use hooks: the words are read here and handed down. */
export function ErrorBoundary({ children, fallback }: { children: ReactNode; fallback?: ReactNode }) {
  const t = useTranslations('errors.boundary')
  return (
    <ErrorBoundaryInner
      fallback={fallback}
      texts={{
        title: t('title'),
        body: (message) => t('body', { message }),
        unexpected: t('unexpected'),
        retry: t('retry'),
      }}
    >
      {children}
    </ErrorBoundaryInner>
  )
}
