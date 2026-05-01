// Firebase Web SDK — solo se inicializa si se proveen variables de entorno web.
// Para el APK nativo, @capacitor-firebase/authentication usa google-services.json directamente.
import { initializeApp, getApps } from 'firebase/app';

if (!getApps().length && import.meta.env.VITE_FIREBASE_API_KEY) {
  initializeApp({
    apiKey:            import.meta.env.VITE_FIREBASE_API_KEY,
    authDomain:        import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId:         import.meta.env.VITE_FIREBASE_PROJECT_ID,
    storageBucket:     import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
    appId:             import.meta.env.VITE_FIREBASE_APP_ID,
  });
}
