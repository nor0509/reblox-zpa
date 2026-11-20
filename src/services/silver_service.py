import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


class SilverTransformService:
    """Przetwarza surowy plik games.parquet (Bronze) do warstwy analitycznej Silver."""

    def __init__(self, input_parquet: Path | str, output_parquet: Path | str) -> None:
        """Inicjalizuje serwis, ustawiając ścieżki pliku wejściowego i wyjściowego."""
        self.input_parquet = Path(input_parquet)
        self.output_parquet = Path(output_parquet)

    def build_silver(self) -> dict[str, int]:
        """Czyści dane, wylicza cechy bezstanowe (bez data leakage) i zapisuje games_silver.parquet."""
        if not self.input_parquet.exists():
            raise FileNotFoundError(
                f"Nie znaleziono pliku źródłowego: {self.input_parquet}. "
                "Uruchom najpierw komendę 'steam-pipeline export'."
            )

        self.output_parquet.parent.mkdir(parents=True, exist_ok=True)

        query = f"""
        CREATE TABLE games_silver AS
        WITH base_cleaned AS (
            SELECT
                app_id,
                NULLIF(TRIM(name), '') AS name,

                -- Korekta flagi is_free: uwzględniamy tag 'Free To Play' w genres
                (is_free OR COALESCE(genres ILIKE '%Free To Play%', FALSE)) AS is_free,

                -- Flaga dla gier wycofanych ze sprzedaży lub tylko w bundlach
                (
                    NOT is_free
                    AND NOT COALESCE(genres ILIKE '%Free To Play%', FALSE)
                    AND price_initial_usd = 0.0
                ) AS is_delisted_or_bundled,

                -- 1. Parsowanie daty wydania
                COALESCE(
                    TRY_STRPTIME(NULLIF(TRIM(release_date), ''), '%d %b, %Y'),
                    TRY_STRPTIME(NULLIF(TRIM(release_date), ''), '%b %d, %Y'),
                    TRY_STRPTIME(NULLIF(TRIM(release_date), ''), '%b %Y')
                )::DATE AS release_date,

                -- 2. Ceny (dla darmowych = 0.0, dla wycofanych ze sprzedaży = NULL)
                CASE
                    WHEN (is_free OR COALESCE(genres ILIKE '%Free To Play%', FALSE)) THEN 0.0
                    WHEN price_initial_usd = 0.0 THEN NULL
                    ELSE price_initial_usd
                END AS price_initial_usd,

                CASE
                    WHEN (is_free OR COALESCE(genres ILIKE '%Free To Play%', FALSE)) THEN 0.0
                    WHEN price_initial_usd = 0.0 THEN NULL
                    ELSE price_final_usd
                END AS price_final_usd,
                discount_percent,

                -- 3. Recenzje i CCU
                positive_reviews,
                negative_reviews,
                (positive_reviews + negative_reviews) AS total_reviews,
                NULLIF(total_recommendations, 0) AS total_recommendations,
                ccu,

                -- 4. Rozbicie tekstowego owners_range ("0 .. 20,000") na liczby
                TRY_CAST(REPLACE(SPLIT_PART(owners_range, ' .. ', 1), ',', '') AS BIGINT)
                    AS owners_min,
                TRY_CAST(REPLACE(SPLIT_PART(owners_range, ' .. ', 2), ',', '') AS BIGINT)
                    AS owners_max,

                -- 5. Metacritic i wiek
                metacritic_score,
                (metacritic_score IS NOT NULL) AS has_metacritic,
                required_age,

                -- 6. Platformy
                windows,
                mac,
                linux,
                (windows::INT + mac::INT + linux::INT) AS platforms_count,

                -- 7. Naprawa pustych stringów ("")
                NULLIF(TRIM(developers), '') AS developers,
                NULLIF(TRIM(publishers), '') AS publishers,
                NULLIF(TRIM(genres), '') AS genres_str,
                NULLIF(TRIM(categories), '') AS categories_str,
                NULLIF(TRIM(short_description), '') AS short_description

            FROM read_parquet('{self.input_parquet.as_posix()}')
            WHERE
                type = 'game'
                AND coming_soon = FALSE
                AND NULLIF(TRIM(name), '') IS NOT NULL
                AND (positive_reviews + negative_reviews) > 0
                AND NOT COALESCE(
                    genres ILIKE '%Utilities%'
                    OR genres ILIKE '%Design & Illustration%'
                    OR genres ILIKE '%Animation & Modeling%'
                    OR genres ILIKE '%Video Production%'
                    OR genres ILIKE '%Audio Production%'
                    OR genres ILIKE '%Software Training%'
                    OR genres ILIKE '%Photo Editing%'
                    OR genres ILIKE '%Accounting%'
                    OR genres ILIKE '%Web Publishing%',
                    FALSE
                )
        ),
        feature_engineered AS (
            SELECT
                *,
                YEAR(release_date) AS release_year,
                MONTH(release_date) AS release_month,
                GREATEST(DATEDIFF('day', release_date, CURRENT_DATE), 1) AS game_age_days,

                -- Stosunki recenzji
                ROUND(positive_reviews::DOUBLE / total_reviews, 4) AS positive_ratio,
                ROUND(positive_reviews::DOUBLE / (negative_reviews + 1), 2) AS pos_neg_ratio,

                -- Dolna granica przedziału ufności Wilsona (95%)
                ROUND(
                    (
                        (positive_reviews::DOUBLE / total_reviews)
                        + (1.96 * 1.96) / (2 * total_reviews)
                        - 1.96 * SQRT(
                            (
                                (positive_reviews::DOUBLE / total_reviews)
                                * (1.0 - (positive_reviews::DOUBLE / total_reviews))
                                + (1.96 * 1.96) / (4 * total_reviews)
                            ) / total_reviews
                        )
                    ) / (1.0 + (1.96 * 1.96) / total_reviews),
                    4
                ) AS wilson_score,

                -- Szacunki właścicieli i przychodów (Metoda Boxleitera)
                ((owners_min + owners_max) / 2)::BIGINT AS owners_midpoint,
                ROUND(total_reviews * 30.0 * price_initial_usd * 0.7, 2) AS estimated_revenue_usd,

                -- Transformacje logarytmiczne ln(x + 1) pod modele ML (bezstanowe)
                ROUND(LN(total_reviews + 1), 4) AS log_total_reviews,
                ROUND(LN(ccu + 1), 4) AS log_ccu,
                ROUND(LN(price_initial_usd + 1), 4) AS log_price_usd,

                -- Rozbicie gatunków i kategorii na listy oraz główny gatunek
                CASE
                    WHEN genres_str IS NOT NULL THEN string_split(genres_str, ', ')
                    ELSE []
                END AS genres_list,
                NULLIF(SPLIT_PART(genres_str, ', ', 1), '') AS primary_genre,
                CASE
                    WHEN categories_str IS NOT NULL THEN string_split(categories_str, ', ')
                    ELSE []
                END AS categories_list,

                -- Flagi binarne cech i mechanik
                COALESCE(genres_str ILIKE '%Indie%', FALSE) AS is_indie,
                COALESCE(genres_str ILIKE '%Early Access%', FALSE) AS is_early_access,
                COALESCE(categories_str ILIKE '%Single-player%', FALSE) AS is_singleplayer,
                COALESCE(categories_str ILIKE '%Multi-player%', FALSE) AS is_multiplayer,
                COALESCE(categories_str ILIKE '%Co-op%', FALSE) AS is_coop,
                COALESCE(categories_str ILIKE '%PvP%', FALSE) AS is_pvp,
                COALESCE(categories_str ILIKE '%controller%', FALSE) AS has_controller_support,
                COALESCE(categories_str ILIKE '%Steam Workshop%', FALSE) AS has_steam_workshop,
                COALESCE(categories_str ILIKE '%VR%', FALSE) AS is_vr_supported,

                CASE
                    WHEN developers IS NOT NULL AND publishers IS NOT NULL
                    THEN (developers = publishers)
                    ELSE NULL
                END AS is_self_published

            FROM base_cleaned
        )
        SELECT
            *,
            ROUND(total_reviews::DOUBLE / game_age_days, 4) AS reviews_per_day,
            ROUND((ccu::DOUBLE / total_reviews) * 1000, 4) AS ccu_per_1k_reviews,

            -- ZMIENNE CELU (TARGET VARIABLES - Y)
            ROUND(LN((estimated_revenue_usd / game_age_days) + 1), 4)
                AS target_log_revenue_per_day,
            ROUND(LN(total_reviews + 1) * (1.0 - positive_ratio), 4)
                AS target_unmet_demand_score,
            (total_reviews >= 1000 AND NOT is_free AND NOT is_delisted_or_bundled)
                AS target_is_commercial_hit,
            (
                is_indie = TRUE
                AND has_metacritic = FALSE
                AND wilson_score >= 0.85
                AND (total_reviews::DOUBLE / game_age_days) >= 1.0
            ) AS target_is_hidden_gem,
            (game_age_days > 365 AND ccu >= 50) AS target_is_evergreen

        FROM feature_engineered;
        """

        conn = duckdb.connect(":memory:")
        try:
            conn.execute(query)
            conn.execute(
                f"COPY games_silver TO '{self.output_parquet.as_posix()}' "
                "(FORMAT PARQUET, COMPRESSION ZSTD);"
            )
            row_count_res = conn.execute("SELECT COUNT(*) FROM games_silver;").fetchone()
            col_count_res = conn.execute("DESCRIBE games_silver;").fetchall()
            rows = int(row_count_res[0]) if row_count_res else 0
            columns = len(col_count_res)
        finally:
            conn.close()

        stats = {"rows": rows, "columns": columns}
        logger.info(
            "Transformacja Silver zakończona: zapisano %d gier (%d kolumn) do %s.",
            stats["rows"],
            stats["columns"],
            self.output_parquet,
        )
        return stats
