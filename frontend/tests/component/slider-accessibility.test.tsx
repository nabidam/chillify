import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Slider } from "@/components/ui/slider";

/**
 * Pins the fix for the axe `aria-input-field-name` (serious) finding: Radix
 * places `role="slider"` on `SliderPrimitive.Thumb`, not on
 * `SliderPrimitive.Root`, so an `aria-label` spread only onto the wrapper's
 * own props never reaches the element that needs an accessible name. The
 * `thumbLabels` prop must forward a name to each thumb by index.
 */
describe("Slider accessibility", () => {
  it("gives the thumb — the element axe inspects for role=slider — its own accessible name", () => {
    render(<Slider aria-label="Seek" thumbLabels={["Seek"]} value={[10]} min={0} max={100} />);

    const slider = screen.getByRole("slider", { name: "Seek" });
    expect(slider).toBeTruthy();
    expect(slider.getAttribute("aria-label")).toBe("Seek");
  });

  it("supports multiple thumbs, each labeled by its own index", () => {
    render(<Slider thumbLabels={["Low", "High"]} value={[10, 90]} min={0} max={100} />);

    expect(screen.getByRole("slider", { name: "Low" })).toBeTruthy();
    expect(screen.getByRole("slider", { name: "High" })).toBeTruthy();
  });

  it("leaves the thumb unlabeled — not crashing — when no thumbLabels are given", () => {
    render(<Slider value={[10]} min={0} max={100} />);

    const sliders = screen.getAllByRole("slider");
    expect(sliders).toHaveLength(1);
    expect(sliders[0]?.hasAttribute("aria-label")).toBe(false);
  });
});
