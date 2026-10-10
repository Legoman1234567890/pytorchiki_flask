import math
import folium
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.io as pio
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, Response
)

from data_loader import load_data

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

app = Flask(__name__)
app.secret_key = "change-me-to-a-real-secret-key"

# ---------- Загрузка данных ----------
df = load_data("production_data_merged.csv")

METRO_MAX_REAL = (
    int(np.nanmax(df["metro_distance_min"]))
    if "metro_distance_min" in df.columns and df["metro_distance_min"].notna().any()
    else 999
)

COLORS_BY_CLASS = {
    "эконом": "gray",
    "комфорт": "blue",
    "комфорт+": "cadetblue",
    "бизнес": "green",
    "премиум": "orange",
    "элит": "red",
    "de luxe": "darkred",
    "не указан": "purple",
}

# ---------- Кэш HTML-содержимого карты ----------
# Заполняется при заходе на /map, отдаётся через /map-frame.
_map_cache = {"html": None}


# ======================== ВСПОМОГАТЕЛЬНЫЕ ========================

def fmt_price(row):
    if pd.notna(row.get("price_mln")):
        return f"{row['price_mln']:.2f} млн ₽"
    if pd.notna(row.get("price_rub")):
        return f"{int(row['price_rub']):,} ₽".replace(",", " ")
    return "цена не указана"


def fmt_metro(row):
    name = row.get("metro_station")
    dist = row.get("metro_distance_min")
    if pd.isna(name) and pd.isna(dist):
        return "нет метро"
    if pd.isna(name):
        return f"{int(dist)} мин"
    if pd.isna(dist):
        return str(name)
    return f"{name} · {int(dist)} мин"


def apply_filters(df_in, args):
    """Применяет фильтры из query-параметров (GET) к DataFrame."""
    f = df_in.copy()

    cities = args.getlist("city")
    if cities:
        f = f[f["city"].isin(cities)]

    sources = args.getlist("source")
    if sources:
        f = f[f["source"].isin(sources)]

    devs = args.getlist("developer")
    if devs:
        f = f[f["developer"].isin(devs)]

    classes = args.getlist("complex_class")
    if classes:
        f = f[f["complex_class"].isin(classes)]

    rooms = [int(r) for r in args.getlist("rooms") if r.isdigit()]
    if rooms:
        f = f[f["rooms"].isin(rooms)]

    def _num(name, default):
        v = args.get(name)
        try:
            return float(v) if v not in (None, "") else default
        except (TypeError, ValueError):
            return default

    price_from = _num("price_from", 0.0)
    price_to = _num("price_to", float(np.nanmax(df["price_mln"])) if df["price_mln"].notna().any() else 0.0)
    if "price_mln" in f.columns:
        f = f[(f["price_mln"].between(price_from, price_to)) | f["price_mln"].isna()]

    floor_from = _num("floor_from", 0)
    floor_to = _num("floor_to", int(np.nanmax(df["floor"])) if df["floor"].notna().any() else 100)
    if "floor" in f.columns:
        f = f[(f["floor"].between(floor_from, floor_to)) | f["floor"].isna()]

    area_from = _num("area_from", 0.0)
    if "total_area" in f.columns and area_from > 0:
        f = f[(f["total_area"] >= area_from) | f["total_area"].isna()]

    metro_from = _num("metro_from", 0)
    metro_to = _num("metro_to", METRO_MAX_REAL)
    metro_filter_active = (metro_from > 0) or (metro_to < METRO_MAX_REAL)

    if "metro_distance_min" in f.columns:
        if metro_filter_active:
            f = f[
                f["metro_distance_min"].notna() &
                f["metro_distance_min"].between(metro_from, metro_to)
            ]
        else:
            f = f[
                f["metro_distance_min"].between(metro_from, metro_to) |
                f["metro_distance_min"].isna()
            ]

    if args.get("mortgage") == "1" and "mortgage_allowed" in f.columns:
        f = f[f["mortgage_allowed"] == True]

    return f.reset_index(drop=True)


def make_options(df_in):
    return {
        "cities": sorted(df_in["city"].dropna().unique().tolist()) if "city" in df_in.columns else [],
        "sources": sorted(df_in["source"].dropna().unique().tolist()) if "source" in df_in.columns else [],
        "developers": sorted(df_in["developer"].dropna().unique().tolist()) if "developer" in df_in.columns else [],
        "classes": sorted(df_in["complex_class"].dropna().unique().tolist()) if "complex_class" in df_in.columns else [],
        "rooms": sorted(df_in["rooms"].dropna().unique().tolist()) if "rooms" in df_in.columns else [],
    }


# ======================== МАРШРУТЫ ========================

@app.route("/")
def index():
    page = int(request.args.get("page", 1))
    page_size = 10

    f = apply_filters(df, request.args)
    total = len(f)
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size

    page_df = f.iloc[start:end]

    cards = []
    for _, row in page_df.iterrows():
        cards.append({
            "id": row["id"],
            "zhk_name": row.get("zhk_name"),
            "developer": row.get("developer"),
            "city": row.get("city"),
            "district": row.get("district"),
            "complex_class": row.get("complex_class"),
            "rooms": row.get("rooms"),
            "total_area": row.get("total_area"),
            "floor": row.get("floor"),
            "total_floors": row.get("total_floors"),
            "price": fmt_price(row),
            "metro": fmt_metro(row),
            "completion_year": row.get("completion_year"),
            "status": row.get("status"),
            "source": row.get("source"),
            "url": row.get("url") if pd.notna(row.get("url")) else None,
        })

    favorites = session.get("favorites", [])

    return render_template(
        "index.html",
        cards=cards,
        total=total,
        total_all=len(df),
        page=page,
        total_pages=total_pages,
        options=make_options(df),
        current_args=request.args,
        metro_max=METRO_MAX_REAL,
        favorites=favorites,
        active_page="index",
    )


@app.route("/map")
def map_view():
    """Строит карту, кладёт её HTML в кэш, отдаёт страницу с iframe."""
    f = apply_filters(df, request.args)
    geo = f.dropna(subset=["lat", "lon"]) if "lat" in f.columns else pd.DataFrame()

    if len(geo) == 0:
        _map_cache["html"] = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
            "<body style='font-family:sans-serif;padding:20px;'>"
            "Нет объектов с координатами под текущие фильтры"
            "</body></html>"
        )
    else:
        center = [geo["lat"].mean(), geo["lon"].mean()]
        m = folium.Map(location=center, zoom_start=10, tiles="OpenStreetMap")

        for _, r in geo.iterrows():
            cls = str(r.get("complex_class", "")).lower()
            color = COLORS_BY_CLASS.get(cls, "purple")

            popup_html = (
                f"<b>{r.get('zhk_name', '—')}</b><br>"
                f"{fmt_price(r)}<br>"
                f"{fmt_metro(r)}<br>"
                f"{r.get('rooms', '—')} комн · {r.get('total_area', '—')} м²<br>"
                f"<a href='/detail/{r['id']}' target='_top'>Открыть карточку →</a>"
            )

            folium.CircleMarker(
                [r["lat"], r["lon"]],
                radius=8,
                color=color,
                fill=True,
                fill_opacity=0.9,
                weight=2,
                tooltip=r.get("zhk_name", "ЖК"),
                popup=folium.Popup(popup_html, max_width=280),
            ).add_to(m)

        _map_cache["html"] = m.get_root().render()

    return render_template(
        "map.html",
        active_page="map",
        options=make_options(df),
        current_args=request.args,
        metro_max=METRO_MAX_REAL,
    )


@app.route("/map-frame")
def map_frame():
    """Отдаёт HTML карты как отдельный документ для iframe."""
    html = _map_cache.get("html")
    if not html:
        return Response(
            "<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
            "<body style='font-family:sans-serif;padding:20px;'>"
            "Карта ещё не сгенерирована. Открой /map."
            "</body></html>",
            mimetype="text/html",
        )
    return Response(html, mimetype="text/html")


@app.route("/detail/<zhk_id>")
def detail(zhk_id):
    row_match = df[df["id"].astype(str) == str(zhk_id)]
    if len(row_match) == 0:
        return render_template("detail.html", row=None, active_page="detail")

    row = row_match.iloc[0]
    favorites = session.get("favorites", [])

    fields = [
        ("Комнат", row.get("rooms")),
        ("Общая площадь", f"{row.get('total_area')} м²" if pd.notna(row.get("total_area")) else "—"),
        ("Жилая площадь", f"{row.get('living_area')} м²" if pd.notna(row.get("living_area")) else "—"),
        ("Кухня", f"{row.get('kitchen_area')} м²" if pd.notna(row.get("kitchen_area")) else "—"),
        ("Этаж", row.get("floor")),
        ("Этажей в доме", row.get("total_floors")),
        ("Потолки", f"{row.get('ceiling_height')} м" if pd.notna(row.get("ceiling_height")) else "—"),
        ("Метро", fmt_metro(row)),
        ("Год сдачи", row.get("completion_year")),
        ("Статус", row.get("status")),
        ("Класс", row.get("complex_class")),
        ("Застройщик", row.get("developer")),
        ("Город", row.get("city")),
        ("Район", row.get("district")),
        ("Отделка", row.get("decoration")),
        ("Источник", row.get("source")),
        ("₽/м²", f"{int(row.get('price_per_sqm')):,}".replace(",", " ") if pd.notna(row.get("price_per_sqm")) else "—"),
    ]

    return render_template(
        "detail.html",
        row={
            "id": row["id"],
            "zhk_name": row.get("zhk_name"),
            "price": fmt_price(row),
            "metro": fmt_metro(row),
            "url": row.get("url") if pd.notna(row.get("url")) else None,
            "source": row.get("source"),
            "is_fav": str(row["id"]) in favorites,
        },
        fields=fields,
        active_page="detail",
    )


@app.route("/favorites")
def favorites_view():
    fav_ids = session.get("favorites", [])
    if not fav_ids:
        fav_df = df.iloc[0:0]
    else:
        fav_df = df[df["id"].astype(str).isin(fav_ids)]

    cards = []
    for _, row in fav_df.iterrows():
        cards.append({
            "id": row["id"],
            "zhk_name": row.get("zhk_name"),
            "developer": row.get("developer"),
            "city": row.get("city"),
            "district": row.get("district"),
            "complex_class": row.get("complex_class"),
            "rooms": row.get("rooms"),
            "total_area": row.get("total_area"),
            "floor": row.get("floor"),
            "total_floors": row.get("total_floors"),
            "price": fmt_price(row),
            "metro": fmt_metro(row),
            "completion_year": row.get("completion_year"),
            "status": row.get("status"),
            "source": row.get("source"),
            "url": row.get("url") if pd.notna(row.get("url")) else None,
        })

    return render_template(
        "favorites.html",
        cards=cards,
        favorites=fav_ids,
        active_page="favorites",
    )


@app.route("/analytics")
def analytics():
    f = apply_filters(df, request.args)

    if len(f) == 0:
        return render_template(
            "analytics.html",
            active_page="analytics",
            empty=True,
            options=make_options(df),
            current_args=request.args,
            metro_max=METRO_MAX_REAL,
        )

    charts = {}

    if "price_mln" in f.columns and f["price_mln"].notna().any():
        fig = px.histogram(f.dropna(subset=["price_mln"]), x="price_mln", nbins=30)
        charts["price_hist"] = pio.to_html(fig, full_html=False, include_plotlyjs="cdn")

    if (
        "complex_class" in f.columns
        and "price_per_sqm" in f.columns
        and f["price_per_sqm"].notna().any()
    ):
        box_df = f.dropna(subset=["price_per_sqm", "complex_class"])
        if len(box_df) > 0:
            fig = px.box(box_df, x="complex_class", y="price_per_sqm")
            charts["price_by_class"] = pio.to_html(fig, full_html=False, include_plotlyjs=False)

    if "city" in f.columns and "price_per_sqm" in f.columns:
        grp = (
            f.dropna(subset=["city", "price_per_sqm"])
            .groupby("city")["price_per_sqm"]
            .mean()
            .sort_values(ascending=False)
            .head(15)
        )
        if len(grp) > 0:
            fig = px.bar(grp.reset_index(), x="city", y="price_per_sqm")
            charts["price_by_city"] = pio.to_html(fig, full_html=False, include_plotlyjs=False)

    if "developer" in f.columns and f["developer"].notna().any():
        counts = f["developer"].value_counts().head(15)
        fig = px.bar(
            counts.reset_index(),
            x="developer", y="count",
            labels={"developer": "Застройщик", "count": "Кол-во ЖК"},
        )
        charts["top_developers"] = pio.to_html(fig, full_html=False, include_plotlyjs=False)

    if "completion_year" in f.columns and f["completion_year"].notna().any():
        counts = f["completion_year"].value_counts().sort_index()
        fig = px.bar(
            counts.reset_index(),
            x="completion_year", y="count",
            labels={"completion_year": "Год сдачи", "count": "Кол-во"},
        )
        charts["by_year"] = pio.to_html(fig, full_html=False, include_plotlyjs=False)

    return render_template(
        "analytics.html",
        charts=charts,
        empty=False,
        options=make_options(df),
        current_args=request.args,
        metro_max=METRO_MAX_REAL,
        active_page="analytics",
    )


# ======================== API: избранное ========================

@app.route("/api/favorite/<zhk_id>", methods=["POST"])
def toggle_favorite(zhk_id):
    favs = set(session.get("favorites", []))
    if zhk_id in favs:
        favs.remove(zhk_id)
        added = False
    else:
        favs.add(zhk_id)
        added = True
    session["favorites"] = list(favs)
    return jsonify({"ok": True, "added": added, "count": len(favs)})


@app.route("/api/favorites/clear", methods=["POST"])
def clear_favorites():
    session["favorites"] = []
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
