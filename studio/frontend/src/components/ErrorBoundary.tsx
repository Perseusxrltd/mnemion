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
    const update = /dynamically imported module|Importing a module script failed|Loading chunk|Unable to preload CSS/i.test(error.message)

    return (
      <div
        className="studio-error"
        role="alert"
      >
        <AlertTriangle size={30} aria-hidden="true" />
        <h2>{update ? 'Reload to open this view' : 'This view could not be displayed'}</h2>
        <p>{update
          ? 'Studio may have updated, or the connection was interrupted. Reload to get the current application.'
          : 'Try opening the view again. If the problem continues, reload Studio.'}</p>
        <div className="studio-error-actions">
          {!update && <button onClick={this.reset}>Try again</button>}
          <button onClick={() => window.location.reload()}><RefreshCw size={14} /> Reload Studio</button>
        </div>
        <small>Reloading clears your connection and any unsaved text in this window.</small>
      </div>
    )
  }
}
