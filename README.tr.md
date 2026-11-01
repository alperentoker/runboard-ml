# runboard

**Plandan makaleye, ön kayıtlı makine öğrenmesi deneyleri.**

runboard kendi bilgisayarında çalışan bir panel. Çalışmanın neyi sorduğunu ve ne beklediğini daha hiçbir şey
eğitmeden yazarsın, planı kilitlersin, deneyleri kendi GPU'nda, Kaggle'da, SSH ile bağlandığın kiralık bir makinede
ya da üniversitenin SLURM kümesinde çalıştırır ve canlı izlersin. Değerlendirmeler gelince runboard her hipotezi
bootstrap güven aralığıyla karara bağlar (*desteklendi*, *reddedildi* ya da *ayırt edilemedi*) ve makalen için
tabloları, yöntem ve sapma bölümlerini ve bir tekrarlanabilirlik kontrol listesini yazar.

Her şey proje klasöründe okunabilir dosyalar olarak durur ve git'e girer: hesap yok, sunucu yok, gizli veritabanı yok.

[![tests](https://github.com/alperentoker/runboard-ml/actions/workflows/tests.yml/badge.svg)](https://github.com/alperentoker/runboard-ml/actions/workflows/tests.yml)
· [English](https://github.com/alperentoker/runboard-ml/blob/main/README.md)
· [Rehber (İngilizce)](https://github.com/alperentoker/runboard-ml/blob/main/docs/tutorial.md)
· [Başvuru](https://github.com/alperentoker/runboard-ml/blob/main/docs/manifest.md)
· [Değişiklikler](https://github.com/alperentoker/runboard-ml/blob/main/CHANGELOG.md)

![İki hipotez %95 aralıklarıyla karara bağlanmış: biri desteklendi, biri reddedildi](https://raw.githubusercontent.com/alperentoker/runboard-ml/main/docs/images/tutorial-7-verdicts.png)

## İçindekiler

- [Neden](#neden)
- [Beş dakikada dene](#beş-dakikada-dene)
- [Bir çalışma nasıl yürür](#bir-çalışma-nasıl-yürür)
- [Bir projede neler var](#bir-projede-neler-var)
- [Hipotez yazmak](#hipotez-yazmak)
- [Koşular nerede çalışır](#koşular-nerede-çalışır)
- [Özellikler](#özellikler)
- [Komut satırı](#komut-satırı)
- [Tablet ve güvenlik](#tablet-ve-güvenlik)
- [Sürekli çalıştırmak](#sürekli-çalıştırmak)
- [Kendi eğitim scriptin](#kendi-eğitim-scriptin)
- [Geliştirme](#geliştirme)

## Neden

Çoğu makine öğrenmesi çalışması, neyin başarı sayılacağına sayıları gördükten sonra karar verir: başka bir metrik,
başka bir seed, bir taban model daha. Deney takip araçları olanı kaydeder ama ne *beklendiğini* kaydetmez; okuyucu
doğrulanmış bir hipotezle sonradan anlatılan bir hikâyeyi ayırt edemez.

runboard ikisini birbirinden ayırır:

| Eğitimden önce | Eğitimden sonra |
| :--- | :--- |
| Sorular, makinenin kontrol edebileceği ölçütler olarak yazılmış hipotezler, değerlendirme protokolü | Her ölçüt değerlendirmeler üzerinde, bootstrap turlarından %95 aralıkla hesaplanır |
| Kilit: zaman, git commit'i ve planın, koşuların ve scriptlerin parmak izleri | Plandaki her sonraki değişiklik, gerekçesiyle, sapma olarak |
| Mühürlü bir test kümesi | Bu kümedeki her değerlendirmenin defteri |

Gerisi (koşuları başlatma, canlı ilerleme, kuyruk, sonuç tabloları) bütün çalışmayı tek araçla yürütebilmen için.

## Beş dakikada dene

```bash
pip install runboard-ml numpy
runboard demo        # ~/runboard-demo içine küçük bir ön kayıtlı çalışma kurar ve panele ekler
runboard             # paneli açar: http://localhost:8000
```

Demo GPU istemez, hiçbir şey indirmez: sentetik veride iki model (doğrusal ve kübik), her biri üç seed'le, iki
hipotez. Planı kilitle, altı koşuyu kuyruğa ekle (her biri yaklaşık on saniye), değerlendir ve kararları oku: bir
hipotez *desteklendi*, öteki *reddedildi* çıkar. [Rehber](https://github.com/alperentoker/runboard-ml/blob/main/docs/tutorial.md)
her ekranı adım adım gösterir.

> PyPI'daki paketin adı **runboard-ml**, çünkü `runboard` adı başka bir projeye ait; komut ve Python modülü `runboard`.
> İkisini aynı ortama kurma. Python 3.11 ya da daha yenisi gerekir; Kaggle istemcisi için `pip install "runboard-ml[kaggle]"`.

## Bir çalışma nasıl yürür

```
 plan.yaml            kilit              koşular              değerlendirme          kararlar             paper/
 sorular,      ──►  plan.lock.json ──►  GPU, Kaggle,     ──►  eval/<koşu>/<küme> ──►  desteklendi /  ──►  tablolar, yöntem,
 hipotezler,        commit +           SSH, SLURM;          ortak turlarda         reddedildi /        sapmalar, kontrol
 protokol           parmak izleri      canlı ilerleme       koşu skorları          ayırt edilemedi     listesi, rapor
```

1. **Plan.** Panelde (*Yeni proje → Ön kayıtlı çalışma*) ya da `plan.yaml`'da: sorular, hipotezler, değerlendirme
   kümeleri ve metrik, ve koşulara (R1, R2, …) dönüşen deney tasarımları.
2. **Kilit.** *Hipotezler → Planı kilitle*. Bundan sonra plan, koşular ve değerlendirme scriptleri sadece yazılı bir
   gerekçeyle değişir; her değişiklik sapma olarak listelenir.
3. **Koşu.** Koşuları herhangi bir ortamda başlat ya da kuyruğa ekle. Panel log'u, epoch'u, batch'i, hızı,
   metrikleri ve kalan süreyi saniye saniye gösterir.
4. **Değerlendirme.** Bir değerlendirme scripti (YOLO için runboard yazar, ya da kendi scriptin) her koşuyu her
   kümede puanlar. Bütün koşular küme başına tek bir yeniden örnekleme planını paylaşır; böylece her koşunun k. bootstrap
   turu aynı görüntüleri kullanır ve koşular arası karşılaştırmalar eşleştirilmiş olur.
5. **Karar.** Hipotezler sayfası her ölçütü tüm kümede ve her turda hesaplar ve kararı aralığıyla verir.
6. **Rapor.** *Makale için dışa aktar* `paper/` klasörünü yazar: Markdown ve LaTeX tablolar, hipotez tablosu, yöntem
   taslağı, sapmalar bölümü, tekrarlanabilirlik listesi, tek sayfalık kayıtlı rapor ve Zenodo için arşiv.

## Bir projede neler var

Proje, içinde `runboard.yaml` olan herhangi bir klasördür. runboard birkaç dosya ekler, senin dosyalarını değiştirmez.

| Dosya | İçeriği | Kilitli |
| :--- | :--- | :---: |
| `runboard.yaml` | koşuların nasıl başladığı (komutlar, ortamlar), neyi raporladıkları, fazlar ve tablolar, işler | hayır |
| `plan.yaml` | sorular, hipotezler, değerlendirme protokolü, seed grupları, kararlar | evet |
| koşu dosyası (`runs.yaml` ya da kendininki) | koşular ve ortak ayarları, senin biçiminde | evet |
| `plan.lock.json` | planın ne zaman, hangi commit'te kilitlendiği ve parmak izleri | bir kez yazılır |
| `deviations.md` | kilitten sonraki her değişiklik, gerekçesi ve diff'iyle | eklenir |
| `eval/` | ortak yeniden örnekleme planları ve her koşunun her kümedeki skorları | — |
| şablon scriptleri | split, check, subsets, evaluate, speed, convert: okuyup değiştirebileceğin sıradan Python | evet |
| `paper/` | *Makale için dışa aktar*'ın yazdıkları | — |

Çalışmanın parçası olmayan durum (koşu kayıtları, loglar, eşleştirilmiş cihazlar) projede değil `~/.runboard`'da durur.

## Hipotez yazmak

Bir hipotez insanlar için bir cümle, makine için bir ölçüttür:

```yaml
hypotheses:
  - id: H1
    question: S1
    text: Sadece karayla eğitilen model hava görüntülerinde, sadece havayla eğitilenin karada çöktüğünden daha çok çöker.
    criterion: "collapse(R4, ground, aerial) > collapse(R5, aerial, ground)"
  - id: H2
    question: S2
    text: Hava verisinin dörtte biri, hava uzmanının %90'ına ulaşır.
    criterion: "R7.aerial >= 0.9 * R5.aerial"
  - id: H3
    question: S2
    text: Doğruluk, hava payının logaritmasıyla artar.
    criterion: "log_fit({R6: 10, R7: 25, R8: 50}, aerial).r2 >= 0.9"
```

`R7.aerial`, R7 koşusunun `aerial` kümesindeki metriğidir; `R7.aerial@person` tek bir sınıftır; `cubic` gibi bir seed
grubu, koşularının ortalamasıdır. Sayılar, `+ - * /`, karşılaştırmalar, `and` ve birkaç fonksiyon (`collapse`, `mean`,
`min`, `max`, `abs`, `log_fit`) kullanılabilir; başka hiçbir şey kullanılamaz ve ölçütler asla Python olarak
çalıştırılmaz. Her ölçüt sen yazarken planlanan koşulara ve kümelere göre kontrol edilir.

Her karşılaştırma bootstrap turlarındaki farkına göre karara bağlanır: %95 aralığın tamamı sıfırın üstündeyse
**desteklendi**, altındaysa **reddedildi**, aksi hâlde **ayırt edilemedi**. Ayrıntılar
[tasarım notlarında](https://github.com/alperentoker/runboard-ml/blob/main/docs/design-v2.md).

## Koşular nerede çalışır

| Ortam | Ne için | Nasıl |
| :--- | :--- | :--- |
| **Yerel** | bu bilgisayarın GPU'su (ya da CPU'su) | panel yeniden başlasa da süren bağımsız bir süreç; durdurulabilir |
| **Kaggle** | ücretsiz bulut GPU (haftada yaklaşık 30 saat) | özel script kernel'leri, canlı log, kuyrukta haftalık kota, yasaklı yol kontrolüyle özel veri yükleme; Python dosyaları gönderilmeden önce derlenir |
| **SSH** | kiralık GPU, laboratuvar sunucusu | kendi `ssh`'ın ve anahtarların (runboard parola görmez); kod tar olarak gönderilir, koşu uzakta bağımsız çalışır, log canlı izlenir, çıktılar eve gelir |
| **SLURM** | üniversite kümesi | giriş düğümünde `sbatch` ile iş, `sacct` ile izleme, `scancel` ile durdurma; kuyruğa istediğin kadar |

Bir proje birkaçını birden kullanabilir; her koşu nerede çalıştığını ve neyle başladığını (commit, commit'lenmemiş
değişiklikler, plan, koşu, script ve veri parmak izleri) kaydeder.

## Özellikler

**Planlama**
- Araştırma sihirbazı: sorular, veri paketleri, deney tasarımları (uzmanlar, veri miktarı eğrisi, mimariler, ablasyon,
  seed tekrarları), protokol ve hipotezler, önerilen ölçütlerle birlikte hazır bir projeye dönüşür.
- Panelde plan düzenleme: koşuları düzenle, kopyala, ekle ve sil; taramalar (değerlerin her kombinasyonu için bir
  koşu), ortak ayarlar ve dosyanın tamamı; her değişiklik önce diff olarak gösterilir ve yedeklenir; başlamış koşular
  ayarlarını korur.

**Çalıştırma**
- Projeler arası tek kuyruk: her ortam boşalınca sıradakini başlatır; Kaggle kotası yetmeyecekse bekler.
- Log satırları arasında canlı ilerleme, yakınlaştırılabilir ve koşular arası karşılaştırmalı metrik ve kayıp
  grafikleri, durduktan sonra kaldığı yerden sürdürme.
- Duman testi: gerçek koşu bulut kotası harcamadan önce az veriyle kısa bir epoch.

**Kod**
- Şablonlar: split (seed'li; videoları ya da sahneleri tek kümede tutar), check (bozuk etiketler, kümeler arası
  sızıntı, benzer görüntüler), convert (COCO / VOC → YOLO), subsets (iç içe veri miktarı listeleri), evaluate (YOLO,
  kararlar için), speed. Bir formdan bir kez yazılır; sen değiştirmedikçe yeniden yazılabilir.
- Kod sayfası: projenin dosyalarını her yerden oku, bu bilgisayardan değiştir; kaydetmeden önce sözdizimi kontrolü.

**Sonuçlar**
- `runboard.yaml`'dan sonuç tabloları ve seed özetleri, kararlarıyla Hipotezler sayfası, makale çıktısı.

**Her yerde**
- Tablet görünümü (`/mini`) ve QR kodla eşleştirme; İngilizce ve Türkçe; açık ve koyu tema.

## Komut satırı

| Komut | Ne yapar |
| :--- | :--- |
| `runboard` / `runboard serve` | paneli (ve bekçisini) başlatır |
| `runboard stop` | ikisini durdurur |
| `runboard demo [klasör]` | beş dakikalık demo çalışmayı kurar |
| `runboard add KLASÖR` / `remove KLASÖR` / `list` | paneldeki projeleri yönetir |
| `runboard lock [klasör]` | planı kilitler |
| `runboard verdicts [klasör]` | her hipotezin kararını yazdırır |
| `runboard export [klasör]` | `paper/` klasörünü yazar |
| `runboard template AD [klasör] --set anahtar=değer` | şablondan bir script yazar |
| `runboard migrate [klasör]` | eski bir projenin kararlarını ve kilidini `plan.yaml`'a taşır |

## Tablet ve güvenlik

runboard varsayılan olarak sadece bu bilgisayarı dinler (`127.0.0.1`) ve hiçbir şey sormaz. Aynı Wi-Fi'daki bir
tabletten izlemek için **Sistem → Tablet erişimi**'ni aç, **Cihaz eşleştir**'e bas ve QR kodu okut ya da 6 haneli kodu
gir (bir kez, iki dakika geçerli). Eşleştirilmiş cihazlar koşuları izleyebilir, başlatıp durdurabilir ve planı
düzenleyebilir; token'lar, yeni projeler, kod, proje dosyası, kilitleme ve klasör tarayıcısı bu bilgisayarda kalır.
Kaggle token'ı `~/.kaggle`'da durur. Ev ağının dışından erişim için Tailscale gibi bir VPN kullan. Bkz.
[SECURITY.md](https://github.com/alperentoker/runboard-ml/blob/main/SECURITY.md).

## Sürekli çalıştırmak

*Sistem → Windows açılınca runboard'u başlat* (Windows), ya da `runboard serve` çalıştıran bir systemd/launchd
servisi. `runboard serve` ayrıca bir bekçi başlatır: panel cevap vermezse yeniden başlatır ve her başlatmayı,
durdurmayı ve hatayı `~/.runboard/server.log`'a yazar.

## Kendi eğitim scriptin

Sihirbazdaki *Kendi eğitim scriptim* herhangi bir scripti koşu başına argümanlarla çalıştırır. Canlı ilerleme için
her olayda bir satır yazdır ya da `rb.py`'yi kullan (sadece standart kütüphane; sihirbaz ve demo scriptlerinin yanına
kopyalar):

```python
import rb
rb.ultralytics(model)            # Ultralytics: tek satır aşağıdakilerin hepsini ekler
rb.start(epochs=100, batches=798)
rb.epoch(3, epochs=100, metrics={"map": 48.2}, best=48.2)
```

Hipotezler için bir değerlendirme, her koşunun skorlarını ortak biçimde `rb.write_eval` (bootstrap turlarındaki
değerler) ya da `rb.write_samples` (öğe başına bir değer) ile yazar. Elle bir proje kısa bir `runboard.yaml`'dır:

```yaml
version: 2
name: Dedektörüm
runs: {file: configs/runs.yaml, section: runs, defaults: train, name: "{id}"}
backends:
  local:  {command: '"{python}" train.py --run {id}', output_dir: runs/local}
  slurm:  {host: login.cluster.edu, sbatch: {partition: gpu, gres: "gpu:1"}, command: 'python train.py --run {id}'}
results:
  report: "{out}/summary.json"
  metrics: {primary: map50_95}
```

Bütün seçenekler [başvuru belgesinde](https://github.com/alperentoker/runboard-ml/blob/main/docs/manifest.md).

## Geliştirme

```bash
git clone https://github.com/alperentoker/runboard-ml
cd runboard-ml
pip install -e .[dev]
pytest                # yaklaşık 200 test; Chrome ya da Edge kuruluysa gerçek bir başsız tarayıcıyla
```

Planlar: [ROADMAP.md](https://github.com/alperentoker/runboard-ml/blob/main/ROADMAP.md) · yayın:
[RELEASING.md](https://github.com/alperentoker/runboard-ml/blob/main/RELEASING.md) · MIT lisanslı.
