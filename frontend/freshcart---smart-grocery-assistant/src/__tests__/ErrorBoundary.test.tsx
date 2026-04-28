/**
 * Tests del ErrorBoundary.
 *
 * Cubre:
 *   - Renderiza hijos cuando no hay error
 *   - Captura errores de renderizado y muestra el fallback por defecto
 *   - Muestra fallback personalizado si se provee
 *   - El botón "Reintentar" resetea el estado de error
 *   - Genera un errorId con formato err_XXXXX
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary } from '../components/ErrorBoundary';

// Componente que lanza un error en el primer render
const Bomb = ({ shouldThrow }: { shouldThrow: boolean }) => {
  if (shouldThrow) throw new Error('Explosión de test');
  return <div>Contenido OK</div>;
};

// Suprimir console.error que React emite internamente al capturar errores en tests
beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ErrorBoundary', () => {
  it('renderiza los hijos cuando no hay error', () => {
    render(
      <ErrorBoundary section="Test">
        <div>Hola mundo</div>
      </ErrorBoundary>
    );
    expect(screen.getByText('Hola mundo')).toBeInTheDocument();
  });

  it('muestra el fallback por defecto al capturar un error', () => {
    render(
      <ErrorBoundary section="TestSection">
        <Bomb shouldThrow />
      </ErrorBoundary>
    );
    expect(screen.getByText('Algo salió mal')).toBeInTheDocument();
  });

  it('muestra el fallback personalizado si se provee', () => {
    render(
      <ErrorBoundary fallback={<div>Mi error custom</div>} section="Custom">
        <Bomb shouldThrow />
      </ErrorBoundary>
    );
    expect(screen.getByText('Mi error custom')).toBeInTheDocument();
  });

  it('muestra el botón Reintentar en el fallback por defecto', () => {
    render(
      <ErrorBoundary section="Test">
        <Bomb shouldThrow />
      </ErrorBoundary>
    );
    expect(screen.getByRole('button', { name: /reintentar/i })).toBeInTheDocument();
  });

  it('muestra una referencia de error con formato err_', () => {
    render(
      <ErrorBoundary section="Test">
        <Bomb shouldThrow />
      </ErrorBoundary>
    );
    const refEl = screen.getByText(/ref:/i);
    expect(refEl.textContent).toMatch(/ref:\s*err_[a-z0-9]+/i);
  });

  it('el botón Reintentar resetea el estado de error y muestra los hijos', () => {
    // Secuencia correcta:
    // 1. Renderizar con error → fallback visible
    // 2. Actualizar el hijo para que NO lance error (React actualiza props en el árbol
    //    pero ErrorBoundary sigue mostrando el fallback porque hasError=true todavía)
    // 3. Hacer clic en "Reintentar" → hasError=false → re-renderiza con el hijo ya corregido
    const { rerender } = render(
      <ErrorBoundary section="Test">
        <Bomb shouldThrow />
      </ErrorBoundary>
    );

    expect(screen.getByText('Algo salió mal')).toBeInTheDocument();

    // Actualizar el árbol con un hijo que no lanza ANTES de hacer clic en Reintentar
    rerender(
      <ErrorBoundary section="Test">
        <Bomb shouldThrow={false} />
      </ErrorBoundary>
    );

    // El ErrorBoundary todavía muestra el fallback (hasError sigue siendo true)
    expect(screen.getByText('Algo salió mal')).toBeInTheDocument();

    // Ahora hacer clic: hasError → false → re-renderiza con Bomb shouldThrow=false → "Contenido OK"
    fireEvent.click(screen.getByRole('button', { name: /reintentar/i }));

    expect(screen.getByText('Contenido OK')).toBeInTheDocument();
  });

  it('no muestra el fallback cuando no hay error', () => {
    render(
      <ErrorBoundary section="Test">
        <div>Todo bien</div>
      </ErrorBoundary>
    );
    expect(screen.queryByText('Algo salió mal')).not.toBeInTheDocument();
  });

  it('incluye el botón Ir al inicio en el fallback por defecto', () => {
    render(
      <ErrorBoundary section="Test">
        <Bomb shouldThrow />
      </ErrorBoundary>
    );
    expect(screen.getByRole('button', { name: /ir al inicio/i })).toBeInTheDocument();
  });
});
