from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from .graphing import (
    build_altitude_profile,
    make_altitude_profile_plot,
    build_time_series,
    make_time_series_plot,
)


def main() -> None:
    # ------------------------------------------------------------
    # 1. CSV PATH
    # ------------------------------------------------------------
    csv_path = Path("C:/Users/grant/OneDrive/School/STAT 370/SOOT_Project/SOOt-project/soot_trimmed.csv")

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    # ------------------------------------------------------------
    # 2. LOAD CSV
    # ------------------------------------------------------------
    print(f"Reading CSV: {csv_path}")
    df = pd.read_csv(csv_path)

    print("\nCSV loaded successfully.")
    print(f"Shape: {df.shape}")

    print("\nColumns:")
    for col in df.columns:
        print(f" - {col}")

    print("\nFirst few rows:")
    print(df.head())

    # ------------------------------------------------------------
    # 3. BUILD A REAL DATETIME COLUMN FROM Time_Mid
    # ------------------------------------------------------------
    df["Time_Mid"] = pd.to_numeric(df["Time_Mid"], errors="coerce")
    df["Datetime_Mid"] = pd.to_datetime(df["Time_Mid"], unit="s", origin="unix")

    print("\nFirst few converted datetimes:")
    print(df[["Time_Mid", "Datetime_Mid"]].head())

    # ------------------------------------------------------------
    # 4. ALTITUDE PROFILE TEST
    # ------------------------------------------------------------
    try:
        print("\nBuilding altitude profile plot...")
        cleaned_alt, profile = build_altitude_profile(
            df,
            alt_col="Altitude_m_MSL",
            ozone_col="Ozone_ppbv",
            bin_m=50,
            window=11,
        )
        make_altitude_profile_plot(
            cleaned_alt,
            profile,
            alt_col="Altitude_m_MSL",
            ozone_col="Ozone_ppbv",
            bin_m=50,
            window=11,
            show_raw=True,
            show_ci=True,
            title="Test: Ozone vs Altitude",
        )
        print("Altitude profile plot built successfully.")
    except Exception as e:
        print(f"Altitude profile plot failed: {e}")

    # ------------------------------------------------------------
    # 5. TIME SERIES TEST
    # ------------------------------------------------------------
    try:
        print("\nBuilding time series plot...")
        cleaned_time, ts_reg, smooth = build_time_series(
            df,
            time_col="Datetime_Mid",
            ozone_col="Ozone_ppbv",
            grid="10s",
            smooth_window=21,
        )
        make_time_series_plot(
            ts_reg,
            smooth,
            grid="10s",
            title="Test: Ozone vs Time",
        )
        print("Time series plot built successfully.")
    except Exception as e:
        print(f"Time series plot failed: {e}")

    # ------------------------------------------------------------
    # 6. SHOW FIGURES
    # ------------------------------------------------------------
    plt.show()


if __name__ == "__main__":
    main()