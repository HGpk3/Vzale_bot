import type { Metadata } from 'next';
import { Bebas_Neue, Space_Grotesk } from 'next/font/google';

import { SessionProvider } from '@/components/session-provider';

import './globals.css';

const heading = Bebas_Neue({ subsets: ['latin'], weight: '400', variable: '--font-heading' });
const body = Space_Grotesk({ subsets: ['latin'], weight: ['400', '500', '700'], variable: '--font-body' });

export const metadata: Metadata = {
  title: 'VZALE | Турнирная платформа',
  description: 'Платформа турниров VZALE: управление, статистика, команды и личный кабинет.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className={`${heading.variable} ${body.variable}`}>
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
