import './globals.css';

export const metadata = {
  title: 'TiDB Oracle',
  description: 'Internal GTM Copilot',
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: 'any' },
      { url: '/tidb-favicon.png', type: 'image/png', sizes: '256x256' },
    ],
    shortcut: '/favicon.ico',
    apple: '/tidb-favicon.png',
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
