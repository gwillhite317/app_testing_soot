# soot_tool/pipeline.py
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import List

import pandas as pd
import requests
from zipfile import ZipFile

from .icartt import ICARTTReader


DOWNLOAD_FILES_URL = "https://asdc.larc.nasa.gov/soot-api/data_files/downloadFiles"


@dataclass
class RunResult:
    df: pd.DataFrame
    ict_files: List[Path]
    rows: int
    cols: int


def _download_and_extract_one(
    session: requests.Session,
    filename: str,
    out_dir: Path,
    session_lock: Lock | None = None,
) -> List[Path]:
    """
    Download one ICT zip and extract it.
    Returns the extracted ICT file paths found after extraction.
    """
    filename = str(filename).strip()
    zip_base = filename.split(".ict")[0]
    zip_path = out_dir / f"{zip_base}.zip"

    # Use a lock around session.get() if you want the safest shared-session behavior.
    # Requests sessions are often used this way in practice, but locking is safer.
    if session_lock is not None:
        with session_lock:
            resp = session.get(
                DOWNLOAD_FILES_URL,
                params={"filenames": filename},
                allow_redirects=True,
                timeout=180,
            )
    else:
        resp = session.get(
            DOWNLOAD_FILES_URL,
            params={"filenames": filename},
            allow_redirects=True,
            timeout=180,
        )

    if resp.status_code != 200:
        raise RuntimeError(
            f"Download failed for {filename} (HTTP {resp.status_code}). "
            f"Response: {(resp.text or '')[:300]}"
        )

    zip_path.write_bytes(resp.content)

    extracted_before = set(out_dir.rglob("*.ict")) | set(out_dir.rglob("*.ICT"))

    with ZipFile(zip_path, "r") as z:
        z.extractall(out_dir)

    zip_path.unlink(missing_ok=True)

    extracted_after = set(out_dir.rglob("*.ict")) | set(out_dir.rglob("*.ICT"))
    new_files = sorted(extracted_after - extracted_before)

    return new_files


def download_and_extract_ict_files(
    session: requests.Session,
    filenames: List[str],
    out_dir: Path,
    *,
    max_workers: int = 4,
) -> List[Path]:
    """
    Download ICT files in parallel using threads.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    filenames = [str(fn).strip() for fn in filenames if str(fn).strip()]
    if not filenames:
        return []

    all_ict_files: List[Path] = []
    session_lock = Lock()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_filename = {
            executor.submit(
                _download_and_extract_one,
                session,
                fn,
                out_dir,
                session_lock,
            ): fn
            for fn in filenames
        }

        for future in as_completed(future_to_filename):
            fn = future_to_filename[future]
            try:
                extracted_files = future.result()
                all_ict_files.extend(extracted_files)
            except Exception as e:
                raise RuntimeError(f"Failed while processing {fn}: {e}") from e

    # Deduplicate in case extraction discovery overlaps
    unique_files = sorted(set(all_ict_files))
    return unique_files


def _add_datetime_columns(df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    fmt = "%Y,%m,%d"

    date_info = meta.get("date_info")
    seconds = meta.get("seconds")

    if not date_info or not seconds:
        return df

    s = ",".join([x.strip() for x in date_info.split(",")[:3]])
    start_date = datetime.strptime(s, fmt)
    start_time = timedelta(seconds=int(seconds))
    start_datetime = start_date + start_time

    time_columns = [col for col in df.columns if "UTC" in str(col).upper()]
    for col in time_columns:
        new_col_name = str(col).replace("UTC", "Datetime")
        df[new_col_name] = start_datetime + pd.to_timedelta(df[col], unit="s")

    if len(time_columns) == 0:
        time_columns = [col for col in df.columns if "TIME" in str(col).upper()]
        for col in time_columns:
            column = str(col).title()
            new_col_name = column.replace("Time", "Datetime")
            df[new_col_name] = start_datetime + pd.to_timedelta(df[col], unit="s")

    return df


def parse_ict_files_to_df(ict_files: List[Path]) -> pd.DataFrame:
    dfs = []

    for p in ict_files:
        r = ICARTTReader(p)
        df = r.read_table()
        meta = r.read_metadata()

        df = _add_datetime_columns(df, meta)
        dfs.append(df)

    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def run_download_convert(
    session: requests.Session,
    filenames: List[str],
    working_dir: Path,
    *,
    cleanup_ict: bool = True,
    max_workers: int = 4,
) -> RunResult:
    ict_files = download_and_extract_ict_files(
        session,
        filenames,
        working_dir,
        max_workers=max_workers,
    )
    df = parse_ict_files_to_df(ict_files)

    if cleanup_ict:
        for p in ict_files:
            try:
                p.unlink()
            except OSError:
                pass

    return RunResult(df=df, ict_files=ict_files, rows=len(df), cols=len(df.columns))