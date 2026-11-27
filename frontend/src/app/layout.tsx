import type { Metadata } from "next";
import "./globals.css";
import { Geist } from "next/font/google";
import { AuthProvider } from "@/components/auth/auth-provider";
import { cn } from "@/lib/utils";

const geist = Geist({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "VagaNexo AI",
  description: "Multi-user candidate profile and resume workspace",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={cn("font-sans", geist.variable)}>
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
