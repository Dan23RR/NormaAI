'use client'

import { Component, type ReactNode } from 'react'
import { Button } from '@/components/ui/Button'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
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
      return (
        <div className="flex min-h-[400px] items-center justify-center p-8">
          <div className="max-w-lg rounded-lg border border-bad/30 bg-surface p-8 text-center">
            <h2 className="text-h3">Questa pagina ha smesso di funzionare</h2>
            <p className="mt-2 text-body text-ink-2">
              {this.state.error?.message || 'Errore imprevisto.'} Riprova; se succede di nuovo, scrivi a
              info@normaai.org con il nome della pagina.
            </p>
            <Button className="mt-6" onClick={() => this.setState({ hasError: false, error: null })}>
              Riprova
            </Button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
