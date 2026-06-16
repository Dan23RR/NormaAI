'use client';

import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <div className="flex items-center justify-center min-h-[400px] p-8">
          <div className="bg-surface border border-red-500/20 rounded-xl p-8 max-w-lg text-center">
            <div className="text-red-400 text-4xl mb-4">!</div>
            <h2 className="text-lg font-semibold text-text mb-2">Si è verificato un errore</h2>
            <p className="text-text-muted text-sm mb-6">
              {this.state.error?.message || 'Errore imprevisto. Riprova.'}
            </p>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="px-4 py-2 bg-accent hover:bg-accent2 text-white rounded-lg text-sm font-medium transition-colors"
            >
              Riprova
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
