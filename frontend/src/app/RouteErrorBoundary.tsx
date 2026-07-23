import { Component, type ReactNode } from "react";
import { useLocation } from "react-router";
import { ErrorState } from "@/features/shared/DataState";

interface InnerProps {
  /** Changes on every navigation so a new screen starts without the old error. */
  resetKey: string;
  children: ReactNode;
}

interface InnerState {
  hasError: boolean;
}

/**
 * Contains a render error to the view that threw it.
 *
 * A screen that throws while rendering must not take the shell, sidebar, or
 * player down with it — those are mounted above this boundary and keep running.
 * The person sees a recoverable message in the content area instead of a blank
 * page, and navigating elsewhere clears it because `resetKey` moves with the
 * route.
 */
class RouteErrorBoundaryInner extends Component<InnerProps, InnerState> {
  override state: InnerState = { hasError: false };

  static getDerivedStateFromError(): InnerState {
    return { hasError: true };
  }

  override componentDidUpdate(previous: InnerProps) {
    if (this.state.hasError && previous.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false });
    }
  }

  private readonly reset = () => {
    this.setState({ hasError: false });
  };

  override render() {
    if (this.state.hasError) {
      return (
        <div className="py-6">
          <ErrorState
            title="This view ran into a problem"
            description="Something on this screen failed to load. Your library and playback are unaffected."
            onRetry={this.reset}
            retryLabel="Reload this view"
          />
        </div>
      );
    }
    return this.props.children;
  }
}

/**
 * Route-scoped error boundary.
 *
 * The class does the catching; this wrapper feeds it the current location key
 * so a route change resets the boundary. React error boundaries must be class
 * components, so this is the smallest such class the app has.
 */
export function RouteErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  return <RouteErrorBoundaryInner resetKey={location.key}>{children}</RouteErrorBoundaryInner>;
}
