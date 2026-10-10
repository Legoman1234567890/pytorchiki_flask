import re
import numpy as np
import pandas as pd


_CORPUS_PATTERN = re.compile(
    r"\s*[\(\[\-–—,:]?\s*"
    r"(корпус|корп\.?|литер|секц(ия|\.)?|блок|строение|стр\.?|этап|очередь)"
    r"\s*[№#]?\s*[\w\d\-–—/]*\s*[\)\]]?\s*$",
    re.IGNORECASE,
)

_CLASS_NORMALIZE = {
    "эконом": "Эконом", "economy": "Эконом",
    "эконом-класс": "Эконом", "эконом класс": "Эконом",
    "комфорт": "Комфорт", "comfort": "Комфорт",
    "комфорт-класс": "Комфорт", "комфорт класс": "Комфорт",
    "комфорт+": "Комфорт+", "комфорт +": "Комфорт+", "comfort+": "Комфорт+",
    "бизнес": "Бизнес", "business": "Бизнес",
    "бизнес-класс": "Бизнес", "бизнес класс": "Бизнес",
    "премиум": "Премиум", "premium": "Премиум", "премиум-класс": "Премиум",
    "элит": "Элит", "элитный": "Элит", "elite": "Элит", "элит-класс": "Элит",
    "de luxe": "De Luxe", "deluxe": "De Luxe", "де люкс": "De Luxe",
}


def normalize_class(val) -> str:
    if not isinstance(val, str):
        return "Не указан"
    key = val.strip().lower()
    if not key or key in ("nan", "none", "нет данных", "не указан"):
        return "Не указан"
    return _CLASS_NORMALIZE.get(key, val.strip().capitalize())


def strip_corpus(name: str) -> str:
    if not isinstance(name, str):
        return ""
    s = name.strip()
    for _ in range(3):
        new_s = _CORPUS_PATTERN.sub("", s).strip(" ,-–—")
        if new_s == s:
            break
        s = new_s
    return s


def extract_zhk_name(row) -> str:
    for col in ("zhk_name", "residential_complex", "project_name", "jk_name", "complex_full_name"):
        val = row.get(col)
        if isinstance(val, str) and val.strip() and val.strip().lower() not in ("nan", "none"):
            return val.strip()

    raw = row.get("complex_name", "")
    cleaned = strip_corpus(raw) if isinstance(raw, str) else ""
    if cleaned:
        return cleaned

    dev = row.get("developer")
    city = row.get("city")
    parts = [p for p in (dev, city) if isinstance(p, str) and p.strip()]
    if parts:
        return " · ".join(parts)

    return "ЖК без названия"


def load_data(csv_path: str = "production_data_merged.csv") -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    num_cols = [
        "price_rub", "price_per_sqm", "price_mln",
        "total_area", "living_area", "kitchen_area",
        "floor", "total_floors", "ceiling_height",
        "metro_distance_min", "completion_year", "build_year",
        "lat", "lon", "views",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if "rooms" in df.columns:
        df["rooms"] = pd.to_numeric(df["rooms"], errors="coerce").fillna(0).astype(int)

    if "price_mln" not in df.columns and "price_rub" in df.columns:
        df["price_mln"] = df["price_rub"] / 1_000_000

    if "price_per_sqm" not in df.columns and "price_rub" in df.columns and "total_area" in df.columns:
        df["price_per_sqm"] = df["price_rub"] / df["total_area"]

    if "metro_distance_min" in df.columns:
        df["metro_distance_min"] = pd.to_numeric(df["metro_distance_min"], errors="coerce")
        df.loc[df["metro_distance_min"] > 90, "metro_distance_min"] = np.nan
        df.loc[df["metro_distance_min"] < 0, "metro_distance_min"] = np.nan

    df = df.loc[:, ~df.columns.duplicated()]

    if "id" not in df.columns:
        df["id"] = df.index.astype(str)
    df["id"] = df["id"].astype(str)

    if "complex_class" in df.columns:
        df["complex_class"] = df["complex_class"].apply(normalize_class)
    else:
        df["complex_class"] = "Не указан"

    df["zhk_name"] = df.apply(extract_zhk_name, axis=1)

    return df