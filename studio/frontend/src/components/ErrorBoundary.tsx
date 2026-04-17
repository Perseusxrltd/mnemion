import { Component, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
  fallback?: (error: Error, reset: () => void) => ReactNode
}

interface State {
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  reset = () => this.setState({ error: null })

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    if (this.props.fallback) return this.props.fallback(error, this.reset)

    return (
      <div
        className="flex-1 flex flex-col items-center justify-center gap-4 p-6"
        style={{ background: 'var(--background-primary)' }}
      >
        <AlertTriangle size={32} style={{ color: '#f97316' }} />
        <div className="text-sm font-semibold" style={{ color: 'var(--text-normal)' }}>
          Something went wrong rendering this view
        </div>
        <pre
          className="text-xs font-mono whitespace-pre-wrap max-w-xl rounded-lg p-3"
          style={{
            background: 'var(--background-secondary)',
            border: '1px solid var(--background-modifier-border)',
            color: 'var(--text-muted)',
            maxHeight: 200,
            overflowY: 'auto',
          }}
        >
          {error.message}
          {error.stack ? '\n\n' + error.stack.split('\n').slice(0, 5).join('\n') : ''}
        </pre>
        <button
          onClick={this.reset}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
          style={{
            background: 'rgba(127,109,242,0.15)',
            color: '#9d8ff9',
            border: '1px solid rgba(127,109,242,0.25)',
          }}
        >
          <RefreshCw size={12} /> Retry
        </button>
      </div>
    )
  }
}
