import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Sidebar from "./components/Sidebar";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} bg-zinc-800 h-full antialiased`}
    >
      <body className="h-full">
        <div className="flex h-screen">
          <Sidebar />
          <main className="flex flex-1 flex-col overflow-hidden bg-zinc-800">
            {/* Draggable top strip; same color as the page background */}
            <div className="drag-region h-10 shrink-0" />
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
