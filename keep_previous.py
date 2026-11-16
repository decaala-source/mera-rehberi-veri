"""Copernicus verisi alınamadığında sitede yayında olan deniz.json ve akinti/*.json dosyalarını out/ klasörüne indirir.
Böylece yalnızca sayfalar güncellenir, uygulama dünkü veriyi kullanmaya devam eder (eskiyse uygulama "Deniz verisi şu an yok" der).
"""
import json
import os
import urllib.request

SITE = 'https://decaala-source.github.io/mera-rehberi-veri'
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')


def get(path):
    try:
        with urllib.request.urlopen(f'{SITE}/{path}', timeout=30) as r:
            data = r.read()
    except Exception as e:  # noqa: BLE001
        print(f'{path}: yok ({e})')
        return
    dest = os.path.join(OUT, *path.split('/'))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, 'wb') as f:
        f.write(data)
    print(f'{path}: korundu ({len(data)} bayt)')


def main():
    pts = json.load(open(os.path.join(HERE, 'points.json'), encoding='utf-8'))
    get('deniz.json')
    for area in pts.get('currents', []):
        get(f"akinti/{area['il']}.json")


if __name__ == '__main__':
    main()
