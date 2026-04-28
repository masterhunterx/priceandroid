import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'cl.freshcart.app',
  appName: 'FreshCart',
  webDir: 'dist',
  server: {
    // En desarrollo local puedes poner tu IP: 'http://192.168.1.X:8000'
    // En producción apunta a tu servidor real.
    // Si está vacío, la app sirve los archivos de dist/ sin servidor externo.
    androidScheme: 'https',
  },
};

export default config;
