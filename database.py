import pandas as pd
from sqlalchemy import create_engine, text

# ==========================================================
# 1. MYSQL CONNECTION & DATABASE CREATION
# ==========================================================
DB_USER = "root"
DB_PASS = "root"  # <-- Replace with your MySQL password
DB_HOST = "localhost"
DB_PORT = "3306"
DB_NAME = "world_bank_ids"

# Connect to MySQL server to create the database if it doesn't exist
server_engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}"
)
with server_engine.begin() as conn:
    conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB_NAME};"))

# Connect directly to the target database
engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ==========================================================
# 2. CREATE RELATIONAL TABLES (PRIMARY & FOREIGN KEYS)
# ==========================================================
ddl_statements = [
    "SET FOREIGN_KEY_CHECKS = 0;",
    "DROP TABLE IF EXISTS footnotes;",
    "DROP TABLE IF EXISTS country_series_metadata;",
    "DROP TABLE IF EXISTS debt_data;",
    "DROP TABLE IF EXISTS indicators;",
    "DROP TABLE IF EXISTS countries;",
    "SET FOREIGN_KEY_CHECKS = 1;",
    """
    CREATE TABLE countries (
        country_code VARCHAR(10) NOT NULL,
        short_name VARCHAR(100),
        long_name VARCHAR(255),
        region VARCHAR(100),
        income_group VARCHAR(100),
        lending_category VARCHAR(50),
        currency_unit VARCHAR(100),
        national_accounts_base_year INT,
        external_debt_reporting_status VARCHAR(50),
        latest_population_census INT NULL,
        latest_trade_data INT NULL,
        latest_water_withdrawal_data INT NULL,
        is_vital_registration_complete TINYINT(1),
        has_special_notes TINYINT(1),
        PRIMARY KEY (country_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE indicators (
        series_code VARCHAR(50) NOT NULL,
        indicator_name VARCHAR(2555) NOT NULL,
        long_definition TEXT,
        topic VARCHAR(2555),
        source VARCHAR(2555),
        dataset VARCHAR(1005),
        periodicity VARCHAR(505),
        aggregation_method VARCHAR(100),
        PRIMARY KEY (series_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE debt_data (
        country_code VARCHAR(10) NOT NULL,
        series_code VARCHAR(500) NOT NULL,
        year SMALLINT NOT NULL,
        debt_value DOUBLE,
        PRIMARY KEY (country_code, series_code, year),
        INDEX idx_debt_year (year),
        INDEX idx_debt_series (series_code),
        CONSTRAINT fk_debt_country
            FOREIGN KEY (country_code) REFERENCES countries(country_code)
            ON UPDATE CASCADE ON DELETE RESTRICT,
        CONSTRAINT fk_debt_indicator
            FOREIGN KEY (series_code) REFERENCES indicators(series_code)
            ON UPDATE CASCADE ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE country_series_metadata (
        country_code VARCHAR(10) NOT NULL,
        series_code VARCHAR(50) NOT NULL,
        description TEXT,
        PRIMARY KEY (country_code, series_code),
        CONSTRAINT fk_csm_country
            FOREIGN KEY (country_code) REFERENCES countries(country_code)
            ON UPDATE CASCADE ON DELETE CASCADE,
        CONSTRAINT fk_csm_indicator
            FOREIGN KEY (series_code) REFERENCES indicators(series_code)
            ON UPDATE CASCADE ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE footnotes (
        country_code VARCHAR(10) NOT NULL,
        series_code VARCHAR(50) NOT NULL,
        year SMALLINT NOT NULL,
        description TEXT,
        PRIMARY KEY (country_code, series_code, year),
        CONSTRAINT fk_fn_country
            FOREIGN KEY (country_code) REFERENCES countries(country_code)
            ON UPDATE CASCADE ON DELETE CASCADE,
        CONSTRAINT fk_fn_indicator
            FOREIGN KEY (series_code) REFERENCES indicators(series_code)
            ON UPDATE CASCADE ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
]

with engine.begin() as conn:
    for stmt in ddl_statements:
        conn.execute(text(stmt))

print("1/6: Relational tables created with PK & FK constraints.")

# ==========================================================
# 3. INSERT PARENT TABLES FIRST (COUNTRIES & INDICATORS)
# ==========================================================
df_countries = pd.read_csv("data/processed/01_country_metadata_cleaned.csv")
year_meta_cols = [
    "latest_population_census",
    "latest_trade_data",
    "latest_water_withdrawal_data",
]
df_countries[year_meta_cols] = df_countries[year_meta_cols].astype("Int64")

df_countries.to_sql("countries", con=engine, if_exists="append", index=False)
print(f"2/6: Inserted {len(df_countries)} rows into 'countries'.")

df_indicators = pd.read_csv("data/processed/05_IDS_SeriesMetaData_cleaned.csv")
df_indicators.to_sql("indicators", con=engine, if_exists="append", index=False)
print(f"3/6: Inserted {len(df_indicators)} rows into 'indicators'.")

# ==========================================================
# 4. UNPIVOT & INSERT CHILD TABLES
# ==========================================================
# A. Debt Data (Wide 2000-2026 columns -> Long format)
df_debt = pd.read_csv("data/processed/03_IDS_ALLCountries_Data_cleaned.csv")
year_cols = [str(y) for y in range(2000, 2027)]

df_debt_long = df_debt.melt(
    id_vars=["country_code", "series_code"],
    value_vars=year_cols,
    var_name="year",
    value_name="debt_value",
)
df_debt_long["year"] = df_debt_long["year"].astype(int)
df_debt_long = df_debt_long.dropna(subset=["debt_value"])

df_debt_long.to_sql(
    "debt_data",
    con=engine,
    if_exists="append",
    index=False,
    chunksize=50000,
    method="multi",
)
print(f"4/6: Inserted {len(df_debt_long):,} rows into 'debt_data'.")

# B. Country-Series Metadata
df_csm = pd.read_csv("data/processed/04_Country_Series_Metadata_cleaned.csv")
df_csm.to_sql(
    "country_series_metadata", con=engine, if_exists="append", index=False
)
print(f"5/6: Inserted {len(df_csm)} rows into 'country_series_metadata'.")

# C. Footnotes
df_fn = pd.read_csv("data/processed/02_FootNoteMetaData_cleaned.csv")
df_fn.to_sql("footnotes", con=engine, if_exists="append", index=False)
print(f"6/6: Inserted {len(df_fn)} rows into 'footnotes'.")

print("\nAll data loaded into MySQL successfully!")