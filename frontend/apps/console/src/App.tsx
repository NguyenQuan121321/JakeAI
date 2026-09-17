import { RouterProvider } from "react-router-dom";
import { ThemeProvider } from "@/context/theme-context";
import { AuthProvider } from "@/context/auth-context";
import { router } from "@/routes";

export default function App() {
  return (
    <ThemeProvider defaultTheme="system" storageKey="jakeai-ui-theme">
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </ThemeProvider>
  );
}
