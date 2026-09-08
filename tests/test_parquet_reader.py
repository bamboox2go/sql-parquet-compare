from __future__ import annotations

import pandas as pd

from sql_parquet_compare.config import StorageConfig
from sql_parquet_compare.parquet_reader import read_parquet


def test_local_single_file_and_directory(tmp_path):
    frame = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})
    file_path = tmp_path / "customers" / "customers.parquet"
    file_path.parent.mkdir()
    frame.to_parquet(file_path, index=False)

    part_dir = tmp_path / "orders"
    part_dir.mkdir()
    frame.iloc[[0]].to_parquet(part_dir / "part-000.parquet", index=False)
    frame.iloc[[1]].to_parquet(part_dir / "part-001.parquet", index=False)

    storage = StorageConfig(backend="local", local_root=str(tmp_path))
    single = read_parquet(storage, "customers/customers.parquet")
    directory = read_parquet(storage, "orders/")

    assert len(single) == 2
    assert len(directory) == 2
    assert set(directory["id"]) == {1, 2}
