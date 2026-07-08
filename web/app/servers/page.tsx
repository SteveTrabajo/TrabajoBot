import { redirect } from "next/navigation";

// The server list lives on the dashboard now.
export default function ServersPage() {
  redirect("/dashboard");
}
