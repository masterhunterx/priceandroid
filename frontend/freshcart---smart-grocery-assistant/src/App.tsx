import React, { useState, useEffect } from 'react';
import { Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import Home from './pages/Home';
import Login from './pages/Login';
import StoreSelect from './pages/StoreSelect';
import SearchResults from './pages/SearchResults';
import ProductDetails from './pages/ProductDetails';
import Categories from './pages/Categories';
import Favorites from './pages/Favorites';
import Notifications from './pages/Notifications';
import BottomNav from './components/BottomNav';
import ProtectedRoute from './components/ProtectedRoute';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Toaster } from 'react-hot-toast';
import { LocationProvider } from './context/LocationContext';
import { ThemeProvider, useTheme } from './context/ThemeContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import SplashScreen from './components/SplashScreen';
import Cart from './pages/Cart';
import { CartProvider } from './context/CartContext';
import FeedbackButton from './components/FeedbackButton';
import OnboardingTour from './components/OnboardingTour';

const PageTransition = ({ children }: { children: React.ReactNode }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -15 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
    >
      {children}
    </motion.div>
  );
};


const AppContent: React.FC = () => {
  const [isAppReady, setIsAppReady] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated, isGuest, logout } = useAuth();

  useEffect(() => {
    function onForceLogout() {
      logout();
      navigate('/login', { replace: true });
    }
    window.addEventListener('freshcart:logout', onForceLogout);
    return () => window.removeEventListener('freshcart:logout', onForceLogout);
  }, [logout, navigate]);

  const isLoginPage = location.pathname === '/login';
  const isStoreSelectPage = location.pathname === '/store-select';

  return (
    <>
      {!isAppReady && !isLoginPage && !isStoreSelectPage && <SplashScreen onComplete={() => setIsAppReady(true)} />}
      <div className={`max-w-md mx-auto min-h-screen relative pb-24 text-slate-900 dark:text-slate-100 transition-opacity duration-700 ${(isAppReady || isLoginPage || isStoreSelectPage) ? 'opacity-100' : 'opacity-0'}`}>
        {/* Gradient glow from store brand color — sits behind all content */}
        <div style={{
          position: 'fixed', top: 0, left: '50%', transform: 'translateX(-50%)',
          width: '100%', maxWidth: '448px', height: '320px',
          background: 'linear-gradient(180deg, var(--store-gradient) 0%, transparent 100%)',
          pointerEvents: 'none', zIndex: 0,
          transition: 'background 0.6s ease',
        }} />

        <AnimatePresence mode="wait">
          {/* key en el wrapper para que AnimatePresence detecte cambios de ruta */}
          <div key={location.pathname} style={{ display: 'contents' }}>
          <Routes location={location}>
            {/* Ruta pública */}
            <Route path="/login" element={<Login />} />

            {/* Selección de tienda — protegida pero sin BottomNav */}
            <Route path="/store-select" element={
              <ProtectedRoute>
                <StoreSelect />
              </ProtectedRoute>
            } />

            {/* Rutas protegidas — cada una envuelta en ErrorBoundary independiente
                para que un crash en ProductDetails no mate Home, SearchResults, etc. */}
            <Route path="/" element={
              <ProtectedRoute>
                <ErrorBoundary section="Home">
                  <PageTransition><Home /></PageTransition>
                </ErrorBoundary>
              </ProtectedRoute>
            } />
            <Route path="/search" element={
              <ProtectedRoute>
                <ErrorBoundary section="SearchResults">
                  <PageTransition><SearchResults /></PageTransition>
                </ErrorBoundary>
              </ProtectedRoute>
            } />
            <Route path="/product/:id" element={
              <ProtectedRoute>
                <ErrorBoundary section="ProductDetails">
                  <PageTransition><ProductDetails /></PageTransition>
                </ErrorBoundary>
              </ProtectedRoute>
            } />
            <Route path="/products/:id" element={
              <ProtectedRoute>
                <ErrorBoundary section="ProductDetails">
                  <PageTransition><ProductDetails /></PageTransition>
                </ErrorBoundary>
              </ProtectedRoute>
            } />
            <Route path="/categories" element={
              <ProtectedRoute>
                <ErrorBoundary section="Categories">
                  <PageTransition><Categories /></PageTransition>
                </ErrorBoundary>
              </ProtectedRoute>
            } />
            <Route path="/favorites" element={
              <ProtectedRoute>
                <ErrorBoundary section="Favorites">
                  <PageTransition><Favorites /></PageTransition>
                </ErrorBoundary>
              </ProtectedRoute>
            } />
            <Route path="/notifications" element={
              <ProtectedRoute>
                <ErrorBoundary section="Notifications">
                  <PageTransition><Notifications /></PageTransition>
                </ErrorBoundary>
              </ProtectedRoute>
            } />
            <Route path="/cart" element={
              <ProtectedRoute>
                <ErrorBoundary section="Cart">
                  <PageTransition><Cart /></PageTransition>
                </ErrorBoundary>
              </ProtectedRoute>
            } />
          </Routes>
          </div>
        </AnimatePresence>
        {(isAuthenticated || isGuest) && !isLoginPage && !isStoreSelectPage && <BottomNav />}
        {isAuthenticated && !isLoginPage && !isStoreSelectPage && <FeedbackButton />}
        {isAuthenticated && !isLoginPage && !isStoreSelectPage && <OnboardingTour />}
        <Toaster position="top-center" reverseOrder={false} />
      </div>
    </>
  );
};

const App: React.FC = () => {
  return (
    // ErrorBoundary raíz: captura fallos en providers o en AppContent completo.
    // Los ErrorBoundary por ruta (dentro de AppContent) son más granulares.
    <ErrorBoundary section="AppRoot">
      <ThemeProvider>
        <AuthProvider>
          <CartProvider>
            <LocationProvider>
              <AppContent />
            </LocationProvider>
          </CartProvider>
        </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
};

export default App;
