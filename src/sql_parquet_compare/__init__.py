"""Like-for-like comparison of SQL Server tables and Azure Storage Parquet files."""

from sql_parquet_compare.comparer import CompareResult, compare_frames

__all__ = ["CompareResult", "compare_frames"]
