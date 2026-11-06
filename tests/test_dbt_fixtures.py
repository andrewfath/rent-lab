"""Build the whole dbt project on synthetic fixtures. Slower; run with `-m dbt`."""

import duckdb
import pytest

from rentlab import config
from rentlab.dbt_runner import TARGETS, run_dbt
from rentlab.fixtures import generate


@pytest.mark.dbt
def test_dbt_build_on_fixtures():
    generate()
    db_path = TARGETS["fixtures"][1]
    db_path.unlink(missing_ok=True)
    assert run_dbt(["build"], target="fixtures"), "dbt build failed; see output above"

    con = duckdb.connect(str(db_path))
    n_rows, comp_coverage = con.execute(
        "select count(*), avg((comp_count > 0)::int) from ml_rent_training"
    ).fetchone()
    con.close()
    assert n_rows > 200
    assert comp_coverage > 0.8
    assert config.FIXTURE_RAW_DIR.exists()
