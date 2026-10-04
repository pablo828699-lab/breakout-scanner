import React from 'react';

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: 24,
          margin: '16px 0',
          borderRadius: 12,
          backgroundColor: '#1e1b4b',
          border: '1px solid #6366f1',
          color: '#e0e7ff',
          fontFamily: 'sans-serif'
        }}>
          <h3 style={{ margin: '0 0 8px 0', color: '#818cf8', fontSize: 16 }}>
            ⚠️ Error en el módulo {this.props.name || ''}
          </h3>
          <p style={{ margin: 0, fontSize: 12, color: '#cbd5e1' }}>
            {this.state.error?.message || 'Error inesperado de renderizado.'}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              marginTop: 12,
              padding: '6px 12px',
              borderRadius: 6,
              backgroundColor: '#6366f1',
              color: '#fff',
              border: 'none',
              cursor: 'pointer',
              fontSize: 12,
              fontWeight: 600
            }}
          >
            Reintentar Render
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
