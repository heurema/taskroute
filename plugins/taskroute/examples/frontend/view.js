export function refreshView(previous, presentIds) {
  return {
    scroll: previous.scroll,
    focus: presentIds.includes(previous.focus) ? previous.focus : null,
    selected: previous.selected.filter((id) => presentIds.includes(id)),
  };
}
