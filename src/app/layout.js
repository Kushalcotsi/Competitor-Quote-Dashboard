import "./globals.css";

export const metadata = {
  title: "WillScot Competitive Analysis",
  description: "Competitive Pricing Intelligence and Dashboard",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
