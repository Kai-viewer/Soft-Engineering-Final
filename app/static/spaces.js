const filter = document.querySelector("#room-filter");
const label = document.querySelector("#room-filter-label");
const rows = document.querySelectorAll("[data-room]");
const empty = document.querySelector("#room-empty");

filter.hidden = false;
label.hidden = false;
filter.addEventListener("input", () => {
  const query = filter.value.trim().toLocaleLowerCase();
  let hasMatch = false;
  for (const row of rows) {
    row.hidden = !row.textContent.toLocaleLowerCase().includes(query);
    hasMatch ||= !row.hidden;
  }
  empty.hidden = hasMatch;
});
