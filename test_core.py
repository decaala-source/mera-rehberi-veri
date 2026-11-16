"""fetch_copernicus.py içindeki saf hesapların denemesi (yalnızca numpy). Çalıştırma: python test_core.py"""
import numpy as np

from fetch_copernicus import align_hourly, local_start, nearest_sea, rounded, speed_dir


def test_nearest_sea():
    lats = np.arange(40.0, 41.0001, 0.025)
    lons = np.arange(28.0, 29.0001, 0.025)
    mask = np.zeros((len(lats), len(lons)), bool)
    mask[:, lons > 28.6] = True  # doğusu deniz
    ij = nearest_sea(lats, lons, mask, 40.5, 28.55, 8)
    assert ij is not None and lons[ij[1]] > 28.6 and abs(lats[ij[0]] - 40.5) < 0.03
    assert nearest_sea(lats, lons, mask, 40.5, 28.0, 8) is None  # 50 km karada
    assert nearest_sea(lats, lons, mask, 43.0, 28.7, 8) is None  # kutunun dışında


def test_align_hourly():
    t0 = np.datetime64('2026-11-16T06:00', 'ns')
    times = t0 + np.array([0, 60, 150, 180], 'timedelta64[m]').astype('timedelta64[ns]')  # 06:00, 07:00, 08:30, 09:00
    vals = np.array([1.0, 2.0, 3.0, 4.0])
    got = align_hourly(times, vals, t0, 4)
    assert got[0] == 1.0 and got[1] == 2.0 and got[3] == 4.0
    assert got[2] == 3.0  # 08:00 için 08:30 (30 dk tolerans içinde)
    got2 = align_hourly(times, vals, t0, 6)
    assert np.isnan(got2[5])  # 11:00 verisi yok


def test_speed_dir():
    s, d = speed_dir(np.array([0.0, 1.0]), np.array([1.0, 0.0]))
    assert abs(s[0] - 3.6) < 1e-9 and abs(d[0] - 0.0) < 1e-9   # kuzeye
    assert abs(d[1] - 90.0) < 1e-9                              # doğuya


def test_rounded_and_start():
    assert rounded(np.array([np.nan, 0.456]), 1) == [None, 0.5]
    assert rounded(np.array([np.nan, np.nan]), 1) is None
    assert rounded(np.array([359.6]), 0) == [360]
    assert local_start(np.datetime64('2026-11-16T22', 'h')) == '2026-11-17T01:00'


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
