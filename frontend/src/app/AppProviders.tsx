import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router";
import { AppRoutes } from "@/app/Router";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Mounted once, above every route. The query client, router, tooltip context,
 * and toaster live here so a route transition never remounts them.
 */
function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Server state is invalidated by SSE, not by polling. Refetching on
        // window focus would fight that and hide staleness the UI must show.
        refetchOnWindowFocus: false,
        retry: 1,
        staleTime: 30_000,
      },
    },
  });
}

const defaultQueryClient = createQueryClient();

export function AppProviders({
  queryClient = defaultQueryClient,
}: {
  queryClient?: QueryClient;
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={200}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export { createQueryClient };
