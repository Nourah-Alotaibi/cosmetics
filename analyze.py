"""Cosmetics EDA with preserved missingness and currency-aware comparisons."""

import argparse, zipfile, io
from pathlib import Path
import numpy as np, pandas as pd
from common import *


def run(data, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if str(data).endswith(".zip"):
        with zipfile.ZipFile(data) as z:
            df = pd.read_csv(io.BytesIO(z.read("output.csv")))
    else:
        df = pd.read_csv(data)
    n = len(df)
    df.columns = df.columns.str.strip().str.lower()
    missing_before = df.isna().sum().to_dict()
    exact_duplicates = int(df.duplicated().sum())
    df = df.drop_duplicates().copy()
    for c in ["brand", "name", "category", "product_type", "currency"]:
        df[c] = df[c].astype("string").str.strip().replace("", pd.NA)
    for c in ["price", "rating"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    invalid_prices = int((df.price < 0).sum())
    invalid_ratings = int(((df.rating < 0) | (df.rating > 5)).sum())
    df.loc[df.price < 0, "price"] = np.nan
    df.loc[(df.rating < 0) | (df.rating > 5), "rating"] = np.nan
    # Missing subcategory is not silently replaced with product_type: they are different fields.
    brands = df.brand.fillna("Unknown").value_counts()
    types = df.product_type.fillna("Unknown").value_counts()
    currencies = df.currency.fillna("Unknown").value_counts()
    brands.rename_axis("brand").reset_index(name="products").to_csv(
        out / "brand_counts.csv", index=False
    )
    types.rename_axis("product_type").reset_index(name="products").to_csv(
        out / "product_type_counts.csv", index=False
    )
    currencies.rename_axis("currency").reset_index(name="products").to_csv(
        out / "currency_counts.csv", index=False
    )
    summary = (
        df.groupby(["currency", "brand"], dropna=False)
        .agg(
            products=("name", "size"),
            median_price=("price", "median"),
            rated_products=("rating", "count"),
            mean_rating=("rating", "mean"),
        )
        .reset_index()
    )
    summary.to_csv(out / "brand_summary_by_currency.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    brands.head(10).sort_values().plot.barh(ax=axes[0], color="#435fa5")
    types.head(10).sort_values().plot.barh(ax=axes[1], color="#7864af")
    axes[0].set_title("Brands by catalog product count")
    axes[1].set_title("Product types by catalog count")
    [ax.set_xlabel("Products") for ax in axes]
    fig.tight_layout()
    fig.savefig(out / "catalog_composition.png")
    plt.close(fig)
    fig, ax = plt.subplots()
    pd.Series(missing_before).sort_values().tail(10).div(n).mul(100).plot.barh(
        ax=ax, color="#b06543"
    )
    ax.set_xlabel("Missing values (%)")
    ax.set_xlim(0, 100)
    ax.set_title("Missingness in the source catalog")
    fig.tight_layout()
    fig.savefig(out / "missingness.png")
    plt.close(fig)
    known = df[df.currency.notna()]
    currency = known.currency.mode().iloc[0] if len(known) else None
    comparable = df[(df.currency == currency) & (df.price > 0) & (df.rating > 0)].copy()
    correlation = (
        float(comparable.price.corr(comparable.rating))
        if len(comparable) >= 3
        else None
    )
    if len(comparable) >= 3:
        fig, ax = plt.subplots()
        ax.scatter(comparable.price, comparable.rating, alpha=0.5, color="#435fa5")
        ax.set_xlabel(f"Price ({currency})")
        ax.set_ylabel("Rating (0–5)")
        ax.set_title(f"Price and rating: {currency}, n={len(comparable)}")
        fig.tight_layout()
        fig.savefig(out / "price_rating.png")
        plt.close(fig)
    report = {
        "dataset": "Local output.csv.zip cosmetics catalog",
        "input_sha256": sha256(data),
        "source_rows": n,
        "clean_rows": len(df),
        "exact_duplicates_removed": exact_duplicates,
        "invalid_prices": invalid_prices,
        "invalid_ratings": invalid_ratings,
        "missing_rating_fraction": float(df.rating.isna().mean()),
        "missing_currency_fraction": float(df.currency.isna().mean()),
        "zero_price_rows": int((df.price == 0).sum()),
        "top_brand": str(brands.index[0]),
        "top_brand_products": int(brands.iloc[0]),
        "top_product_type": str(types.index[0]),
        "price_rating_currency": str(currency),
        "price_rating_n": len(comparable),
        "price_rating_pearson_r": correlation,
        "limitations": [
            "Catalog coverage is not sales or market share.",
            "Prices are summarized within currency; no unsupported currency conversion.",
            "Missing/zero prices and missing ratings limit value comparisons.",
            "Correlation does not establish a price effect on ratings.",
        ],
        "environment": versions(),
    }
    save_json(out / "metrics.json", report)
    print(report)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--out", default="results")
    a = p.parse_args()
    run(a.data, a.out)
