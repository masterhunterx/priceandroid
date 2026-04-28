import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** Render alternativo personalizado. Si se omite, muestra el fallback default. */
  fallback?: ReactNode;
  /** Nombre de la sección para el log (ej: "ProductDetails", "SearchResults"). */
  section?: string;
}

interface State {
  hasError: boolean;
  errorId: string;
}

/**
 * ErrorBoundary de clase — captura errores de renderizado en el subárbol.
 * React solo permite class components para getDerivedStateFromError/componentDidCatch.
 *
 * Uso:
 *   <ErrorBoundary section="ProductDetails">
 *     <ProductDetails />
 *   </ErrorBoundary>
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, errorId: '' };
  }

  static getDerivedStateFromError(): State {
    const errorId = `err_${Date.now().toString(36)}`;
    return { hasError: true, errorId };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    const section = this.props.section ?? 'unknown';
    console.error(`[ErrorBoundary:${section}] id=${this.state.errorId}`, error, info.componentStack);
  }

  private handleReload = () => {
    this.setState({ hasError: false, errorId: '' });
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    if (this.props.fallback) return this.props.fallback;

    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-5 p-8 text-center">
        <span className="material-symbols-outlined text-6xl text-red-400 select-none">
          sentiment_very_dissatisfied
        </span>
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-1">
            Algo salió mal
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 max-w-xs mx-auto">
            Ocurrió un error inesperado en esta sección. El resto de la app sigue funcionando.
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={this.handleReload}
            className="bg-primary text-background-dark font-bold px-5 py-2.5 rounded-xl text-sm active:scale-95 transition-all"
          >
            Reintentar
          </button>
          <button
            onClick={() => window.location.href = '/'}
            className="bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-bold px-5 py-2.5 rounded-xl text-sm active:scale-95 transition-all"
          >
            Ir al inicio
          </button>
        </div>
        <p className="text-[10px] text-slate-400 font-mono">ref: {this.state.errorId}</p>
      </div>
    );
  }
}
