// Home page: instant search and browser-stored favourites.
const search = document.getElementById("game-search");
const grid = document.getElementById("game-grid");
const empty = document.getElementById("game-empty");
const FAV_KEY = "ella.favourites";

const favourites = new Set(JSON.parse(localStorage.getItem(FAV_KEY) || "[]"));

function paintFavourites() {
  document.querySelectorAll(".fav").forEach((button) => {
    const on = favourites.has(button.dataset.slug);
    button.classList.toggle("on", on);
    button.textContent = on ? "★" : "☆";
  });
}

if (search && grid) {
  search.addEventListener("input", () => {
    const term = search.value.trim().toLowerCase();
    let visible = 0;
    grid.querySelectorAll(".game-card").forEach((card) => {
      const match = card.dataset.name.includes(term);
      card.hidden = !match;
      if (match) visible += 1;
    });
    empty.hidden = visible > 0;
  });
}

grid?.addEventListener("click", (event) => {
  const button = event.target.closest(".fav");
  if (!button) return;
  event.preventDefault();
  const slug = button.dataset.slug;
  if (favourites.has(slug)) favourites.delete(slug);
  else favourites.add(slug);
  localStorage.setItem(FAV_KEY, JSON.stringify([...favourites]));
  paintFavourites();
});

paintFavourites();
