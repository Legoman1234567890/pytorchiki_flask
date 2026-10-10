// ============ Поиск в мультиселектах (Choices.js) ============
document.querySelectorAll("select.js-searchable").forEach(el => {
    new Choices(el, {
        removeItemButton: true,
        searchEnabled: true,
        searchPlaceholderValue: el.dataset.placeholder || "Поиск…",
        noResultsText: "Ничего не найдено",
        noChoicesText: "Нет вариантов",
        itemSelectText: "",
        shouldSort: false,
        placeholder: true,
        placeholderValue: el.dataset.placeholder || "",
    });
});
// ============ Избранное ============
async function toggleFavorite(id, btn) {
    try {
        const resp = await fetch(`/api/favorite/${id}`, { method: "POST" });
        const data = await resp.json();
        if (!data.ok) return;

        // Обновляем кнопку
        if (data.added) {
            btn.classList.add("fav-active");
            btn.textContent = btn.classList.contains("fav-btn-large")
                ? "💔 Убрать из избранного"
                : "💔 Убрать";
        } else {
            btn.classList.remove("fav-active");
            btn.textContent = btn.classList.contains("fav-btn-large")
                ? "❤ В избранное"
                : "❤ В избранное";
        }

        // Обновляем счётчик в шапке
        const counter = document.getElementById("fav-count");
        if (counter) counter.textContent = data.count;

        // Если мы на странице избранного и убрали — перезагрузим
        if (window.location.pathname === "/favorites" && !data.added) {
            window.location.reload();
        }
    } catch (e) {
        console.error(e);
    }
}

document.querySelectorAll(".fav-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const id = btn.dataset.id;
        if (id) toggleFavorite(id, btn);
    });
});

// ============ Очистка избранного ============
const clearBtn = document.getElementById("clear-favs");
if (clearBtn) {
    clearBtn.addEventListener("click", async () => {
        if (!confirm("Очистить всё избранное?")) return;
        await fetch("/api/favorites/clear", { method: "POST" });
        window.location.reload();
    });
}
