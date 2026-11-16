"""Mera Rehberi deniz verisi: E.U. Copernicus Marine Service'ten günlük tahmin, uygulamanın okuyacağı küçük JSON dosyalarına.

GitHub Actions her gün çalıştırır (.github/workflows/deniz.yml). Kimlik bilgileri GitHub Secrets'ta:
  COPERNICUSMARINE_SERVICE_USERNAME, COPERNICUSMARINE_SERVICE_PASSWORD  (copernicusmarine aracı bunları kendisi okur)

Girdi:  points.json   (uygulamadan üretilir: npm run sea-points)
Çıktı:  out/deniz.json          bütün noktaların saatlik dalga (w, m), su sıcaklığı (t, °C), akıntı hızı (s, km/s) ve yönü (d, gittiği yön, derece)
        out/akinti/<il>.json    ilin akıntı ızgarası (karadaki hücreler atılır)

Kaynaklar (öncelik sırasıyla; bir nokta ilk kapsayan kaynaktan doldurulur):
  dalga:     Karadeniz 2,5 km (Marmara'nın kuzeyi dahil, 40,5°K üstü)  →  Akdeniz 4,2 km
  sıcaklık:  Marmara 500 m  →  Karadeniz 2,5 km  →  Akdeniz 4,2 km
  akıntı:    Marmara 500 m  →  Karadeniz 2,5 km  →  Akdeniz 4,2 km
Kıyı hücreleri modelde boş olabilir; nokta, en yakın deniz hücresinden (en çok MAX_KM) okunur.

Atıf (lisans gereği uygulamada gösterilir): "Generated using E.U. Copernicus Marine Service Information".
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
HOURS = 168          # 7 gün, saatlik
TZ_HOURS = 3         # Türkiye, yıl boyu UTC+3

# (veri kümesi kimlikleri; sürüm eki yok, araç güncel sürümü seçer), değişkenler, kapsama kutusu, derinlik var mı, en çok uzaklık km
WAVE_SOURCES = [
    (['cmems_mod_blk_wav_anfc_2.5km_PT1H-i'], ['VHM0'], (40.5, 47.33, 27.25, 42.0), False, 8),
    (['cmems_mod_med_wav_anfc_4.2km_PT1H-i'], ['VHM0'], (30.19, 45.98, -18.13, 36.29), False, 12),
]
TEMP_SOURCES = [
    (['cmems_mod_blk_phy-temp_anfc_mrm-500m_PT1H-i', 'cmems_mod_blk_phy-tem_anfc_mrm-500m_PT1H-i'], ['thetao'], (39.5, 41.5, 25.0, 30.0), True, 4),
    (['cmems_mod_blk_phy-temp_anfc_2.5km_PT1H-m', 'cmems_mod_blk_phy-tem_anfc_2.5km_PT1H-m'], ['thetao'], (40.5, 47.33, 27.25, 42.0), True, 8),
    (['cmems_mod_med_phy-temp_anfc_4.2km-2D_PT1H-m', 'cmems_mod_med_phy-tem_anfc_4.2km-2D_PT1H-m'], ['thetao'], (30.19, 45.98, -17.29, 36.29), False, 12),
]
CURRENT_SOURCES = [
    (['cmems_mod_blk_phy-cur_anfc_mrm-500m_PT1H-i'], ['uo', 'vo'], (39.5, 41.5, 25.0, 30.0), True, 4),
    (['cmems_mod_blk_phy-cur_anfc_2.5km_PT1H-m'], ['uo', 'vo'], (40.5, 47.33, 27.25, 42.0), True, 8),
    (['cmems_mod_med_phy-cur_anfc_4.2km-2D_PT1H-m'], ['uo', 'vo'], (30.19, 45.98, -17.29, 36.29), False, 12),
]


# ---------------------------------------------------------------- saf hesap (numpy; test_core.py dener)

def km_between(lat1, lon1, lat2, lon2):
    """Yaklaşık uzaklık (km), küçük mesafeler için"""
    kx = math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot((lon2 - lon1) * kx, lat2 - lat1) * 111.32


def nearest_sea(lats, lons, sea_mask, lat, lon, max_km):
    """En yakın deniz hücresinin (i, j) indeksi; `max_km` içinde yoksa None. sea_mask: [lat, lon] bool"""
    if not (lats.min() - 0.5 <= lat <= lats.max() + 0.5 and lons.min() - 0.5 <= lon <= lons.max() + 0.5):
        return None
    i0 = int(np.abs(lats - lat).argmin())
    j0 = int(np.abs(lons - lon).argmin())
    dlat = abs(float(lats[1] - lats[0])) if len(lats) > 1 else 0.05
    dlon = abs(float(lons[1] - lons[0])) if len(lons) > 1 else 0.05
    r_i = int(math.ceil(max_km / (dlat * 111.32))) + 1
    r_j = int(math.ceil(max_km / (dlon * 111.32 * max(0.2, math.cos(math.radians(lat)))))) + 1
    best, best_d = None, max_km + 1e-9
    for i in range(max(0, i0 - r_i), min(len(lats), i0 + r_i + 1)):
        for j in range(max(0, j0 - r_j), min(len(lons), j0 + r_j + 1)):
            if not sea_mask[i, j]:
                continue
            d = km_between(lat, lon, float(lats[i]), float(lons[j]))
            if d <= best_d:
                best, best_d = (i, j), d
    return best


def align_hourly(times_utc, values, t0_utc, hours, tol_minutes=31):
    """Saatlik ortak eksene hizalar: her saat için en yakın zaman (tolerans içinde), yoksa NaN.
    times_utc: datetime64[ns] dizisi, values: [time] ya da [time, p]"""
    target = t0_utc + np.arange(hours) * np.timedelta64(1, 'h')
    idx = np.searchsorted(times_utc, target)
    out_shape = (hours,) + values.shape[1:]
    out = np.full(out_shape, np.nan, dtype=float)
    tol = np.timedelta64(tol_minutes, 'm')
    for k, t in enumerate(target):
        cand = [c for c in (idx[k] - 1, idx[k]) if 0 <= c < len(times_utc)]
        if not cand:
            continue
        c = min(cand, key=lambda x: abs(times_utc[x] - t))
        if abs(times_utc[c] - t) <= tol:
            out[k] = values[c]
    return out


def speed_dir(u, v):
    """m/s bileşenlerden hız (km/s) ve gittiği yön (derece, kuzeyden saat yönünde)"""
    speed = np.hypot(u, v) * 3.6
    direction = (np.degrees(np.arctan2(u, v)) + 360.0) % 360.0
    return speed, direction


def rounded(arr, nd):
    """JSON için: NaN → None, yuvarlanmış liste; tamamen boşsa None"""
    out = [None if (x is None or not np.isfinite(x)) else (round(float(x), nd) if nd else int(round(float(x)))) for x in arr]
    return out if any(x is not None for x in out) else None


def local_start(t0_utc):
    """UTC başlangıç → yerel (UTC+3) 'YYYY-MM-DDTHH:00'"""
    t = t0_utc.astype('datetime64[h]').astype(dt.datetime) + dt.timedelta(hours=TZ_HOURS)
    return t.strftime('%Y-%m-%dT%H:00')


def fill(target, key, values):
    """Henüz dolmamış (tamamen NaN) noktayı doldurur"""
    cur = target.get(key)
    if cur is None or np.all(np.isnan(cur)):
        target[key] = values


# ---------------------------------------------------------------- Copernicus (copernicusmarine + xarray)

def annotate(level, msg):
    """GitHub Actions açıklaması: herkese açık depoda giriş yapmadan da okunur (tek satır)"""
    print(f'::{level}::' + ' | '.join(str(msg).splitlines())[:900], flush=True)


class LoginError(Exception):
    """Copernicus kullanıcı adı/parola reddedildi: diğer ürünleri denemenin anlamı yok"""


def is_login_error(e):
    s = str(e).lower()
    return 'credential' in s or 'unauthorized' in s or '401' in s or 'invalid username' in s


def open_ds(ids, variables, bbox, t0, t1, has_depth):
    import copernicusmarine  # noqa: PLC0415  (yalnızca Actions'ta kurulu)
    last = None
    for ds_id in ids:
        kw = dict(dataset_id=ds_id, variables=variables,
                  minimum_latitude=bbox[0], maximum_latitude=bbox[1], minimum_longitude=bbox[2], maximum_longitude=bbox[3],
                  start_datetime=str(t0), end_datetime=str(t1))
        if has_depth:
            kw.update(minimum_depth=0, maximum_depth=2)
        try:
            ds = copernicusmarine.open_dataset(**kw)
        except Exception as e:  # kimlik bulunamadı ya da sürüm değişti: sıradakini dene
            last = e
            continue
        if 'depth' in ds.dims:
            ds = ds.isel(depth=0)
        return ds_id, ds
    raise RuntimeError(f'Veri kümesi açılamadı: {ids}: {last}')


def clip_bbox(src, need):
    """Kaynak kutusu ile gerekli kutunun kesişimi; kesişmiyorsa None"""
    la0, la1 = max(src[0], need[0]), min(src[1], need[1])
    lo0, lo1 = max(src[2], need[2]), min(src[3], need[3])
    return (la0, la1, lo0, lo1) if la0 < la1 and lo0 < lo1 else None


def extract(sources, points, t0, t1, log):
    """points: [(key, lat, lon)] → {key: {var: ndarray[HOURS]}} (her kaynak yalnızca boş kalanları doldurur)"""
    import xarray as xr  # noqa: PLC0415
    result = {}
    lats_all = [p[1] for p in points]
    lons_all = [p[2] for p in points]
    need = (min(lats_all) - 0.3, max(lats_all) + 0.3, min(lons_all) - 0.3, max(lons_all) + 0.3)
    for ids, variables, src_box, has_depth, max_km in sources:
        box = clip_bbox(src_box, need)
        if not box:
            continue
        try:
            ds_id, ds = open_ds(ids, variables, box, t0, t1, has_depth)
        except Exception as e:
            if is_login_error(e):
                raise LoginError(str(e)) from e
            log(f'  ATLANDI {ids[0]}: {e}')
            annotate('warning', f'{ids[0]} açılamadı: {e}')
            continue
        lats, lons = ds['latitude'].values, ds['longitude'].values
        first = ds[variables[0]].isel(time=0).values
        mask = np.isfinite(first)
        picks = []
        for key, lat, lon in points:
            done = result.get(key)
            if done and all(np.isfinite(done[v]).any() for v in variables):
                continue
            ij = nearest_sea(lats, lons, mask, lat, lon, max_km)
            if ij:
                picks.append((key, ij))
        log(f'  {ds_id}: {len(picks)} nokta')
        if not picks:
            continue
        ii = xr.DataArray([p[1][0] for p in picks], dims='p')
        jj = xr.DataArray([p[1][1] for p in picks], dims='p')
        times = ds['time'].values.astype('datetime64[ns]')
        for var in variables:
            vals = ds[var].isel(latitude=ii, longitude=jj).values  # [time, p]
            aligned = align_hourly(times, vals, np.datetime64(t0, 'ns'), HOURS)
            for k, (key, _) in enumerate(picks):
                result.setdefault(key, {})
                fill(result[key], var, aligned[:, k])
    return result


def main(argv):
    out_dir = os.path.join(HERE, 'out')
    os.makedirs(os.path.join(out_dir, 'akinti'), exist_ok=True)
    pts = json.load(open(os.path.join(HERE, 'points.json'), encoding='utf-8'))
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    t0 = np.datetime64(now, 'h')
    t1 = t0 + np.timedelta64(HOURS - 1, 'h')
    log = lambda m: print(m, flush=True)  # noqa: E731

    points = [(p['key'], p['lat'], p['lon']) for p in pts['points']]
    cells = []
    for area in pts['currents']:
        for k, (lat, lon) in enumerate(area['cells']):
            cells.append((f"c:{area['il']}:{k}", lat, lon))

    log('Dalga'); waves = extract(WAVE_SOURCES, points, t0, t1, log)
    log('Sıcaklık'); temps = extract(TEMP_SOURCES, points, t0, t1, log)
    log('Akıntı'); curs = extract(CURRENT_SOURCES, points + cells, t0, t1, log)

    start = local_start(t0)
    generated = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    sea = {'v': 1, 'generatedAt': generated, 'start': start, 'hours': HOURS,
           'source': 'Generated using E.U. Copernicus Marine Service Information', 'points': {}}
    for key, _, _ in points:
        rec = {}
        w = waves.get(key, {}).get('VHM0')
        t = temps.get(key, {}).get('thetao')
        c = curs.get(key, {})
        if w is not None and (r := rounded(w, 1)): rec['w'] = r
        if t is not None and (r := rounded(t, 1)): rec['t'] = r
        if 'uo' in c and 'vo' in c:
            s, d = speed_dir(c['uo'], c['vo'])
            if (rs := rounded(s, 1)): rec['s'] = rs; rec['d'] = rounded(d, 0)
        if rec:
            sea['points'][key] = rec
    with open(os.path.join(out_dir, 'deniz.json'), 'w', encoding='utf-8') as f:
        json.dump(sea, f, ensure_ascii=False, separators=(',', ':'))
    log(f"deniz.json: {len(sea['points'])}/{len(points)} nokta")

    for area in pts['currents']:
        out_cells = []
        for k, (lat, lon) in enumerate(area['cells']):
            c = curs.get(f"c:{area['il']}:{k}", {})
            if 'uo' not in c or 'vo' not in c:
                continue
            s, d = speed_dir(c['uo'], c['vo'])
            rs = rounded(s, 1)
            if rs:
                out_cells.append({'lat': lat, 'lon': lon, 's': rs, 'd': rounded(d, 0)})
        with open(os.path.join(out_dir, 'akinti', f"{area['il']}.json"), 'w', encoding='utf-8') as f:
            json.dump({'v': 1, 'generatedAt': generated, 'start': start, 'hours': HOURS, 'cells': out_cells}, f, separators=(',', ':'))
        log(f"akinti/{area['il']}.json: {len(out_cells)} hücre")
    return 0 if sea['points'] else 1


if __name__ == '__main__':
    try:
        code = main(sys.argv[1:])
    except LoginError as e:
        annotate('error', 'Copernicus girişi reddedildi. COPERNICUSMARINE_SERVICE_USERNAME / PASSWORD secret değerlerini '
                 've Copernicus hesabının e-posta onayını kontrol et. Ayrıntı: ' + str(e)[:300])
        sys.exit(2)
    except Exception as e:  # noqa: BLE001
        import traceback
        annotate('error', f'{type(e).__name__}: {e} | ' + traceback.format_exc()[-600:])
        raise
    if code:
        annotate('error', 'Hiçbir noktaya veri yazılamadı (yukarıdaki uyarılara bak).')
    sys.exit(code)
