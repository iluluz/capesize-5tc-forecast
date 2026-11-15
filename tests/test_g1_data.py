"""Gate G1 on the real workbooks. Skipped when the data folder is not available (e.g. in CI)."""
import pytest

pytest.importorskip("openpyxl")

from capesize import config as C  # noqa: E402


def _have_data() -> bool:
    try:
        for n in (1, 2, 3, 4, 6):
            C.workbook(n)
        return True
    except FileNotFoundError:
        return False


pytestmark = pytest.mark.skipif(not _have_data(), reason="workbooks not found (set CAPESIZE_DATA_DIR)")


@pytest.fixture(scope="module")
def store():
    from capesize import features as F
    from capesize.targets import build_targets
    g, X, A, srcs, _ = F.build_feature_store()
    return g, X, A, srcs, build_targets(g["S"], C.HORIZONS + C.STRETCH_HORIZONS)


def test_g1_point_in_time(store):
    from capesize.checks import g1_checks
    g, X, A, srcs, Y = store
    assert all(v == "PASS" for v in g1_checks(g, X, A, srcs, Y, C.HORIZONS + C.STRETCH_HORIZONS).values())


def test_g1_negative_control_detects_leak(store):
    from capesize.checks import leak_control
    g, _, _, srcs, _ = store
    assert leak_control(g, srcs) > 100
