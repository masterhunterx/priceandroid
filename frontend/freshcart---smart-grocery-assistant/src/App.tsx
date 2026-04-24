import React, { useState } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import Home from './pages/Home';
import Login from './pages/Login';
import SearchResults from './pages/SearchResults';
import ProductDetails from './pages/ProductDetails';
import Categories from './pages/Categories';
import Favorites from './pages/Favorites';
import Notifications from './pages/Notifications';
import BottomNav from './components/BottomNav';
import ProtectedRoute from './components/ProtectedRoute';
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
  const { isAuthenticated } = useAuth();

  const isLoginPage = location.pathname === '/login';

  return (
    <>
      {!isAppReady && !isLoginPage && <SplashScreen onComplete={() => setIsAppReady(true)} />}
      <div className={`max-w-md mx-auto min-h-screen relative pb-24 text-slate-900 dark:text-slate-100 transition-opacity duration-700 ${(isAppReady || isLoginPage) ? 'opacity-100' : 'opacity-0'}`}>

        <AnimatePresence mode="wait">
          {/* key en el wrapper para que AnimatePresence detecte cambios de ruta */}
          <div key={location.pathname} style={{ display: 'contents' }}>
          <Routes location={location}>
            {/* Ruta pública */}
            <Route path="/login" element={<Login />} />

            {/* Rutas protegidas */}
            <Route path="/" element={
              <ProtectedRoute>
                <PageTransition><Home /></PageTransition>
              </ProtectedRoute>
            } />
            <Route path="/search" element={
              <ProtectedRoute>
                <PageTransition><SearchResults /></PageTransition>
              </ProtectedRoute>
            } />
            <Route path="/product/:id" element={
              <ProtectedRoute>
                <PageTransition><ProductDetails /></PageTransition>
              </ProtectedRoute>
            } />
            <Route path="/products/:id" element={
              <ProtectedRoute>
                <PageTransition><ProductDetails /></PageTransition>
              </ProtectedRoute>
            } />
            <Route path="/categories" element={
              <ProtectedRoute>
                <PageTransition><Categories /></PageTransition>
              </ProtectedRoute>
            } />
            <Route path="/favorites" element={
              <ProtectedRoute>
                <PageTransition><Favorites /></PageTransition>
              </ProtectedRoute>
            } />
            <Route path="/notifications" element={
              <ProtectedRoute>
                <PageTransition><Notifications /></PageTransition>
              </ProtectedRoute>
            } />
            <Route path="/cart" element={
              <ProtectedRoute>
                <PageTransition><Cart /></PageTransition>
              </ProtectedRoute>
            } />
          </Routes>
          </div>
        </AnimatePresence>
        {isAuthenticated && !isLoginPage && <BottomNav />}
        {isAuthenticated && !isLoginPage && <FeedbackButton />}
        {isAuthenticated && !isLoginPage && <OnboardingTour />}
        <Toaster position="top-center" reverseOrder={false} />
      </div>
    </>
  );
};

const App: React.FC = () => {
  return (
    <ThemeProvider>
      <AuthProvider>
        <CartProvider>
          <LocationProvider>
            <AppContent />
          </LocationProvider>
        </CartProvider>
      </AuthProvider>
    </ThemeProvider>
  );
};

export default App;
