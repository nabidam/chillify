import { useCallback, useRef } from "react";

/**
 * Return focus to the control that opened a dialog once it closes.
 *
 * Radix restores focus to a `DialogTrigger`; the app opens dialogs from state
 * rather than triggers, so Radix has no trigger to return to and focus falls to
 * the document body. This hook captures whatever was focused at the moment the
 * dialog opened — the invoking button, in practice — and hands back an
 * `onCloseAutoFocus` handler that puts focus back there.
 *
 * The opener is captured on the rising edge of `open`, during render and before
 * Radix's own focus move runs in an effect, so it is still the invoking control
 * and not the dialog's first field. If that control has since left the DOM (a
 * menu item that unmounted, say) the handler stands aside and lets Radix decide,
 * rather than focusing a detached node.
 */
export function useRestoreFocusOnClose(open: boolean): (event: Event) => void {
  const openerRef = useRef<HTMLElement | null>(null);
  const wasOpenRef = useRef(false);

  if (open && !wasOpenRef.current && typeof document !== "undefined") {
    const active = document.activeElement;
    openerRef.current = active instanceof HTMLElement ? active : null;
  }
  wasOpenRef.current = open;

  return useCallback((event: Event) => {
    const opener = openerRef.current;
    if (opener?.isConnected) {
      event.preventDefault();
      opener.focus();
    }
  }, []);
}
