import { expect, test } from "vitest";
import { refreshView } from "./view.js";

test("refresh preserves view state and drops only removed row identities", () => {
  const before = { scroll: 240, focus: "row-8", selected: ["row-8", "removed"] };
  expect(refreshView(before, ["row-8", "row-9"])).toEqual({
    scroll: 240, focus: "row-8", selected: ["row-8"],
  });
  expect(refreshView(before, ["row-9"]).focus).toBe(null);
  expect(before.selected).toEqual(["row-8", "removed"]);
});
