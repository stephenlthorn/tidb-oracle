import './globals.css';

export const metadata = {
  title: 'TiDB Oracle',
  description: 'Internal GTM Copilot',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
