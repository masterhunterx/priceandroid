import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'cl.freshcart.app',
  appName: 'FreshCart',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
  },
  plugins: {
    GoogleAuth: {
      scopes: ['profile', 'email'],
      serverClientId: '145660625437-vutld3gc335dr9jkohsgjgstmkd2msv8.apps.googleusercontent.com',
      forceCodeForRefreshToken: true,
    },
  },
};

export default config;
