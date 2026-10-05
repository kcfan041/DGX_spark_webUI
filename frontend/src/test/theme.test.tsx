import "@/i18n";
import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { ColorSchemeToggle } from "@/components/ColorSchemeToggle";
import zhTW from "@/i18n/locales/zh-TW.json";

describe("ColorSchemeToggle", () => {
  beforeEach(() => localStorage.clear());

  it("toggles between light and dark and persists the choice", () => {
    render(
      <MantineProvider defaultColorScheme="light">
        <ColorSchemeToggle />
      </MantineProvider>,
    );
    const btn = screen.getByTestId("theme-toggle");
    expect(btn).toHaveAccessibleName(zhTW.theme.toDark);
    fireEvent.click(btn);
    expect(document.documentElement).toHaveAttribute("data-mantine-color-scheme", "dark");
    expect(localStorage.getItem("mantine-color-scheme-value")).toBe("dark");
    expect(btn).toHaveAccessibleName(zhTW.theme.toLight);
    fireEvent.click(btn);
    expect(document.documentElement).toHaveAttribute("data-mantine-color-scheme", "light");
    expect(localStorage.getItem("mantine-color-scheme-value")).toBe("light");
  });
});
