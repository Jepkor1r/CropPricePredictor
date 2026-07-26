import { DashboardShell } from "@/components/dashboard/Shell";
import { getDashboard } from "@/lib/data";

export const metadata = { title: "Dashboard — PriceCast" };

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const data = await getDashboard();
  return <DashboardShell generatedAt={data.generatedAt}>{children}</DashboardShell>;
}
