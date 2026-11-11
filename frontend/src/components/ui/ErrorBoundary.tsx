import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "./Button";

interface Props {
  children: ReactNode;
  /** Changing this clears the error, so moving to another page recovers without a reload. */
  resetKey: string;
}

interface State {
  error: Error | null;
  resetKey: string;
}

/** Keeps a crash on one page from blanking the whole app. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, resetKey: this.props.resetKey };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey === state.resetKey ? null : { error: null, resetKey: props.resetKey };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("page_crashed", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="rounded-xl border border-line bg-surface px-6 py-12 text-center">
        <h1 className="text-base font-semibold">Something went wrong on this page</h1>
        <p className="mt-1.5 text-sm text-ink-muted">
          Your data is safe. Reload the page, or open another one from the menu.
        </p>
        <Button className="mt-5" onClick={() => window.location.reload()}>
          Reload
        </Button>
      </div>
    );
  }
}
