import "./style.css";
import { refreshView } from "./view.js";

const rows = document.querySelector("#rows");
const ids = Array.from({ length: 80 }, (_, index) => `row-${index}`);
function render() {
  rows.innerHTML = ids.map((id) => `<label><input id="${id}" type="checkbox">${id}</label>`).join("");
}
render();
document.querySelector("#refresh").addEventListener("click", () => {
  const next = refreshView({
    scroll: rows.scrollTop,
    focus: document.activeElement.id,
    selected: [...rows.querySelectorAll("input:checked")].map((input) => input.id),
  }, ids);
  render();
  for (const id of next.selected) document.getElementById(id).checked = true;
  if (next.focus) document.getElementById(next.focus).focus({ preventScroll: true });
  rows.scrollTop = next.scroll;
});

if (new URL(location.href).searchParams.has("acceptance")) {
  try {
    const selected = document.getElementById("row-8");
    selected.checked = true;
    selected.focus({ preventScroll: true });
    rows.scrollTop = 240;
    document.querySelector("#refresh").click();
    if (!document.getElementById("row-8").checked || document.activeElement.id !== "row-8" || rows.scrollTop !== 240) {
      throw new Error("View state lost after refresh");
    }
    document.body.dataset.browserAcceptance = "PASS";
  } catch (error) {
    document.body.dataset.browserAcceptance = "FAIL";
    document.body.dataset.failure = error.message;
  }
}
