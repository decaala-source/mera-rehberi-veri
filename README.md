# Mera Rehberi veri sitesi

Bu klasör, GitHub'daki **mera-rehberi-veri** deposunun içeriğidir (herkese açık depo; içinde yalnızca veri işi ve sayfalar var, uygulama kodu yok).

- Her sabah 06:30'da GitHub Actions, E.U. Copernicus Marine Service'ten dalga, su sıcaklığı ve akıntı tahminini alır.
- Sonuç ve sayfalar GitHub Pages'te yayınlanır: https://decaala-source.github.io/mera-rehberi-veri/
  - `deniz.json`, `akinti/<il>.json`: uygulamanın okuduğu deniz verisi
  - `gizlilik.html`, `kvkk.html`, `kosullar.html`, `destek.html`: App Store'un istediği sayfalar

## Dosyalar
| Dosya | Ne işe yarar |
|---|---|
| `fetch_copernicus.py` | Copernicus'tan veriyi alıp JSON'a çeviren betik |
| `test_core.py` | Betiğin hesaplarını dener (her çalışmada önce bu çalışır) |
| `points.json` | Hangi noktaların verisi alınacak (uygulamadan üretilir: `npm run sea-points`) |
| `site/` | Gizlilik, KVKK, koşullar, destek sayfaları (uygulama klasöründe `python scripts/build-site.py`) |
| `.github/workflows/deniz.yml` | Günlük işin ayarı |

## Kurulum (bir kez)
1. GitHub'da yeni, **Public** bir depo aç: adı `mera-rehberi-veri`.
2. Bu klasörün içeriğini depoya yükle.
3. Depoda **Settings > Secrets and variables > Actions > New repository secret** ile iki gizli değer ekle:
   - `COPERNICUSMARINE_SERVICE_USERNAME`: Copernicus kullanıcı adın
   - `COPERNICUSMARINE_SERVICE_PASSWORD`: Copernicus şifren
   Bu değerler yalnızca GitHub'da şifreli durur; dosyalara yazılmaz, kimse göremez.
4. **Settings > Pages > Build and deployment > Source**: "GitHub Actions" seç.
5. **Actions** sekmesinde "Deniz verisi" işini aç, **Run workflow** ile ilk kez elle çalıştır. 10-20 dakika sürer.

## Mera ya da sayfa metni değişince
Uygulama klasöründe `npm run sea-points` ve `python scripts/build-site.py` çalıştırılır; değişen `points.json` ve `site/` bu depoya yüklenir.
