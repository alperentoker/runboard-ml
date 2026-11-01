# runboard

**Plandan makaleye, ön kayıtlı makine öğrenmesi deneyleri.** Sorularını ve hipotezlerini yaz, planı kilitle,
deneyleri kendi GPU'nda, Kaggle'da, SSH ile bağlandığın bir makinede ya da SLURM kümesinde çalıştır, canlı izle; her
hipotez bootstrap güven aralığıyla karara bağlansın, makale için tablolar, yöntem ve sapma bölümleri hazır olsun.
Bütün projelerin için kendi bilgisayarında çalışan tek bir panel; her şey reponda okunabilir dosyalar olarak durur.

**Yeni misin?** `pip install runboard-ml numpy`, ardından `runboard demo`: herhangi bir işlemcide beş dakikalık ön kayıtlı bir
çalışma; adım adım anlatımı [docs/tutorial.md](docs/tutorial.md)'de.

[English](README.md) · [![tests](https://github.com/alperentoker/runboard-ml/actions/workflows/tests.yml/badge.svg)](https://github.com/alperentoker/runboard-ml/actions/workflows/tests.yml)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/run-dark.png">
  <img alt="Bir koşunun sayfası: canlı ilerleme, sonuçlar ve eğitim eğrileri" src="docs/images/run-light.png">
</picture>

<table><tr>
<td width="50%">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/home-dark.png">
  <img alt="Projeler ana sayfası" src="docs/images/home-light.png">
</picture>

<sub>Projeler ana sayfası</sub>
</td>
<td width="50%">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/plan-dark.png">
  <img alt="Koşu planını düzenleme: her değişiklik değiştireceği satırlarla önizlenir" src="docs/images/plan-light.png">
</picture>

<sub>Plan düzenleme: değişecek satırların önizlemesi</sub>
</td>
</tr></table>

- **Projeler ana sayfası** — her proje bir kart: aktif koşunun canlı ilerlemesi, planın tamamlanma oranı, en iyi skor.
- **Canlı koşular** — log akışı, log satırları arasında saniyelik tahmin, metrik ve kayıp grafikleri, koşu karşılaştırma.
- **Hesaplama ortamları** — Kaggle Notebooks (özel kernel, canlı log, haftalık GPU kotası, veri yükleme; Kaggle koşusu panelden iptal edilemez, *Kaggle'da aç* ile Kaggle'da durdurulur) yerel GPU (panelden bağımsız çalışır, panel yeniden başlasa da sürer, durdurulabilir), SSH ile bağlanılan bir makine (kiralık GPU, laboratuvar sunucusu) ve SLURM kümesi (sbatch ile; kendi SSH anahtarlarınla, runboard parola görmez). Arayüz küçük; Colab planlanıyor.
- **Ön kayda uygun** — planlanan koşuları ve ortak ayarları kilitle, açıkça işaretli ek deneyler ekle, kararları ("kazanan mimari" gibi) dayandıkları sayılarla kaydet.
- **Plan düzenleme** — koşuları, ortak ayarları ya da koşu dosyasının tamamını panelden düzenle, kopyala, ekle; yalnızca değişen satırlar değişir, her değişiklik önce fark olarak gösterilir, başlamış koşular ayarlarını korur.
- **Tarama ve kuyruk** — değerlerin her kombinasyonu için bir taslak koşu; ortam boşalınca sıradaki koşuyu başlatan, Kaggle kotası yetmeyecekse bekleyen ortam başına bir kuyruk.
- **Sonuçlar** — proje tanımında belirlenen tablolar, eğriler ve tohum varyansı özetleri.
- **Tablet görünümü** — `/mini`, küçük pencere (picture-in-picture) desteğiyle; ana ekrana eklenebilir. Tablet bir kez QR kodla eşleşir.
- **English / Türkçe** arayüz.

Gizli bilgiler bilgisayarından çıkmaz: Kaggle token'ı `~/.kaggle` altında, eşleşmiş cihazlar ve bütün durum
`~/.runboard` altında kalır; hiçbiri proje deposuna girmez.

## Kurulum

```bash
pip install runboard-ml            # Kaggle için: pip install "runboard-ml[kaggle]"
runboard                           # http://localhost:8000 — yalnızca bu bilgisayar, şifre yok
```

PyPI'daki paketin adı `runboard-ml` (`runboard` adı başka bir projeye ait); komut ve Python modülü `runboard`. İkisini
aynı ortama kurma: aynı modül adını paylaşırlar. Python 3.11 ya da daha yenisi gerekir.

Sonra panelde:

1. **Sistem → Bağlantılar → Kaggle** (yalnızca bulut GPU istiyorsan): panel, kaggle.com'da token oluşturmayı adım adım
   anlatır; token bir kez yapıştırılır. Bu bilgisayarda `~/.kaggle/access_token` dosyasına kaydedilir, test edilir ve
   bir daha gösterilmez.
2. **Yeni proje**: klasörü seç; *Ön kayıtlı çalışma (YOLO)*, *YOLO eğitimi (kod gerekmez)* ya da *Kendi eğitim betiğim*
   türünü, sonra nerede çalışacağını seç (bu bilgisayar, Kaggle, SSH, SLURM). runboard klasöre `runboard.yaml`, koşu
   dosyasını ve YOLO için eğitim ve değerlendirme scriptlerini yazar; senin dosyalarını değiştirmez.

İçinde zaten `runboard.yaml` olan bir klasör aynı sihirbazdan ya da `runboard add KLASÖR` ile eklenir.

Proje tanımının bütün seçenekleri [docs/manifest.md](docs/manifest.md) içinde; çalıştırılabilir bir örnek
[examples/yolo-quickstart](examples/yolo-quickstart) klasöründe.

## Tablet erişimi

runboard varsayılan olarak yalnızca bu bilgisayarda (`127.0.0.1`) dinler ve hiçbir şey sormaz. Aynı Wi-Fi'deki bir
tabletten izlemek için **Sistem → Tablet erişimi**'ni aç (panel bütün ağ arayüzlerinde yeniden başlar), **Cihaz
eşleştir**'e bas ve QR kodu tabletle okut; ya da gösterilen adresi açıp 6 haneli kodu yaz. Kod bir kez ve iki dakika
geçerlidir. Eşleşmiş cihazlar orada listelenir ve istendiğinde kaldırılır.

Eşleşmiş cihaz koşuları izleyebilir, başlatıp durdurabilir. Kaggle token'ı girmek, proje eklemek, klasör gezgini ve
başlangıç ayarı bu bilgisayarda kalır. Ev ağı dışından erişim için Tailscale gibi bir VPN kullan ve makine adını
`~/.runboard/config.yaml` içindeki `allowed_hosts`'a ekle. Ayrıntılar: [SECURITY.md](SECURITY.md).

## İlerleme bildirme

Eğitim betiğinden her olay için bir satır yaz ya da [`runboard/rb.py`](runboard/rb.py) dosyasını (yalnızca standart
kütüphane) betiğin yanına kopyala. Ultralytics için `rb.ultralytics(model)` tek satırda her şeyi ekler. Her çağrı
`@@rb {json}` satırı basar; kendi log satırların değişmez. Düz metin logları olan projeler bunları düzenli ifadelerle
(`progress.patterns`) tarif edebilir.

MIT lisanslıdır.
