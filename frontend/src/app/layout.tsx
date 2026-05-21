import type { Metadata } from 'next';
import { EmergencyStopBar } from '@/components/EmergencyStopBar';
import './globals.css';

export const metadata: Metadata = {
  title: 'bt_execution_gui',
  description: 'ROS2 Behavior Tree 운영 GUI',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>
        <EmergencyStopBar />
        <main className="relative mx-auto max-w-[1280px] px-6 py-10">
          {children}
        </main>
      </body>
    </html>
  );
}
