# freebuff-9router — راهنمای فارسی

اتصال مدل‌های رایگان کدنویسی **FreeBuff** (GLM 5.3 Flash، DeepSeek V4 Flash، MiMo، Solar Pro و…)
به **ناین‌روتر** به‌عنوان یک پرووایدر استاندارد، با استفاده از
**freebuff-proxy** به‌عنوان گیت‌وی محلی.

```
ابزارهای شما (Hermes / OpenCode / Cline / aider / codex / هر کلاینت OpenAI)
        │
        ▼
9Router  (localhost:20128 — پیشوند: freebuff/*)
        │  سازگار با OpenAI — Bearer = توکن FreeBuff شما
        ▼
freebuff-proxy  (127.0.0.1:3457 — حالت bridge)
        │  ترجمه پروتکل + مدیریت سشن مطابق CLI رسمی
        ▼
codebuff.com  (سرویس FreeBuff)
```

## چه چیزی می‌گیرید؟

- مدل‌های `freebuff/<model-id>` روی `GET /v1/models` ناین‌روتر — صفحه‌ی پرووایدر
  در داشبورد برای هر مدل یک سوییچ کم/زیاد می‌دهد (لیست از ردیف‌های
  `customModels`، وضعیت روشن/خاموش از `disabledModels`) و فهرست `/model`
  دقیقاً و زنده تابع همین سوییچ‌هاست: مدلی را خاموش کنید، بلافاصله از همه
  pickerها ناپدید می‌شود و روتر درخواستش را با HTTP 400 رد می‌کند.
- برای هر اکانت FreeBuff یک **connection** در ناین‌روتر ساخته می‌شود؛ چرخش بین
  اکانت‌ها با مکانیزم بومی ناین‌روتر انجام می‌شود (همان الگوی چند اکانت Cline).
- **حالت Bridge سرتاسری**: توکن FreeBuff فقط در SQLite ناین‌روتر می‌ماند و
  درخواست‌به‌درخواست رله می‌شود؛ پراکسی هیچ توکنی ذخیره نمی‌کند.
- **بدون هیچ پچی در ناین‌روتر.** همه‌چیز از مکانیزم رسمی `openai-compatible`
  خود ناین‌روتر استفاده می‌کند (همان ردیف‌هایی که داشبورد می‌نویسد)، پس
  `npm i -g 9router` چیزی را پاک نمی‌کند.
- ابزارهای idempotent: ثبت، افزودن اکانت، راستی‌آزمایی، وضعیت، حذف.

## پیش‌نیازها

- لینوکس (amd64/arm64) یا مک، با دسترسی root/sudo
- [ناین‌روتر](https://www.npmjs.com/package/9router) نصب و در حال اجرا
- Go ≥ 1.26 و Node ≥ 20 فقط برای بیلد (`install.sh` خودش مدیریت می‌کند)
- یک اکانت GitHub برای تأیید توکن FreeBuff (فقط یک کلیک در مرورگر)

## راه‌اندازی سریع

```bash
git clone https://github.com/98H/freebuff-9router.git
cd freebuff-9router
sudo ./install.sh            # بیلد + نصب پراکسی + ثبت پرووایدر در ناین‌روتر
```

آخر کار، نصب‌کننده یک **لینک ورود** چاپ می‌کند. آن را باز کنید و با اکانت
GitHub موردنظر وارد شوید — توکن خودکار گرفته و ثبت می‌شود.

راستی‌آزمایی:

```bash
python3 freebuff9r.py status
python3 freebuff9r.py verify --router-key <کلید API ناین‌روتر> \
        --model freebuff/z-ai/glm-5.3-flash --prompt "say hi"
```

### افزودن اکانت جدید

```bash
python3 freebuff9r.py login-url        # لینک ورود + شناسه‌های جریان چاپ می‌شود
# لینک را در پنجره خصوصی باز کنید و با اکانت GitHub دیگری وارد شوید، سپس:
python3 freebuff9r.py wait-login --fingerprint <FP> --hash <HASH> --expires-at <EXP>
```

هر اکانت = یک connection زیر همان پیشوند `freebuff`.

## نصب‌کننده دقیقاً چه می‌کند؟

1. `freebuff-proxy` را از تگ منتشرشده upstream بیلد و در `/usr/local/bin/` نصب می‌کند.
2. سرویس systemd با سخت‌گیری امنیتی می‌سازد: یوزر سیستمی مجزا،
   `ProtectSystem=strict`، اتصال فقط روی loopback (`127.0.0.1:3457`)،
   `SAFE_MODE=true`، `COST_MODE=free`، حالت bridge (بدون `AUTH_TOKENS`).
3. از `~/.9router/db/data.sqlite` بکاپ می‌گیرد و سپس provider node و
   connection را با `freebuff9r.py` ثبت می‌کند (ردیف‌های SQLite دقیقاً
   همان‌هایی که داشبورد ناین‌روتر می‌نویسد — بدون پچ باندل، مقاوم به آپدیت).
4. جریان ورود FreeBuff را شروع می‌کند و لینک را به شما می‌دهد.

## چرا با آپدیت ناین‌روتر از بین نمی‌رود؟

| داده | محل ذخیره | بعد از `npm i -g 9router` |
|---|---|---|
| provider node + connections | `~/.9router/db/data.sqlite` (بیرون از node_modules) | ✅ می‌ماند |
| توکن‌های FreeBuff | `providerConnections.data.apiKey` (همان دیتابیس) | ✅ می‌ماند |
| فهرست مدل‌ها | درخواست‌به‌درخواست از `/v1/models` پراکسی | ✅ همیشه تازه |
| باینری و سرویس پراکسی | `/usr/local/bin` + systemd | ✅ مستقل از ناین‌روتر |
| تنظیمات پراکسی | `/etc/freebuff-proxy/env` (سطح دسترسی 0600) | ✅ می‌ماند |

هیچ فایلی داخل درخت نصب ناین‌روتر تغییر نمی‌کند. ناین‌روتر در هر درخواست
`providerConnections` را از SQLite می‌خواند، پس ثبت نیاز به ری‌استارت ندارد.
بعد از هر آپدیت ناین‌روتر فقط `python3 freebuff9r.py status` را بزنید.

## حذف کامل

```bash
sudo systemctl disable --now freebuff-proxy
python3 freebuff9r.py remove
```

دستور `remove` فقط ردیف‌های ساخته‌شده توسط همین ابزار را پاک می‌کند و قبل از
آن یک بکاپ زمان‌دار از دیتابیس می‌گیرد.

## امنیت و ریسک‌ها (صادقانه)

**نکات مثبت این استک**

- پراکسی فقط روی `127.0.0.1` گوش می‌دهد؛ داشبورد ادمین (`/admin` با توکن قوی
  تصادفی) هم loopback-only است. برای دیدنش: `ssh -L 3457:127.0.0.1:3457 host`
- در حالت bridge توکن‌ها فقط یک‌جا (دیتابیس ناین‌روتر با دسترسی 0600) ذخیره
  می‌شوند — همان جایی که توکن‌های بقیه پرووایدرها هست.
- هیچ رمزی در این ریپازیتوری کامیت نمی‌شود.

**چیزهایی که باید بپذیرید**

- **ریسک نقض قوانین سرویس:** خود upstream هشدار می‌دهد که استفاده از توکن‌های
  FreeBuff از طریق پراکسی نقض ToS است و اکانت ممکن است بن شود. اکانتی استفاده
  کنید که از دست دادنش برایتان مشکلی ندارد.
- **پرامپت‌های شما به سرورهای Codebuff می‌روند** — دقیقاً مثل استفاده از CLI
  رسمی. کد محرمانه، پسورد و کلید نفرستید.
- قابلیت‌های ضدبن (`SAFE_MODE`، jitter، rotation) ریسک را کم می‌کنند اما صفر
  نمی‌کنند؛ کیفیت IP اهمیت زیادی دارد.

## عیب‌یابی

| علامت | معنی / راه‌حل |
|---|---|
| مدل‌های `freebuff/*` در `/v1/models` نیستند | پراکسی Down؟ `systemctl status freebuff-proxy` و `python3 freebuff9r.py status` |
| خطای `502 upstream_auth_rejected` | توکن آن connection منقضی/باطل شده — جریان login را با `--replace` تکرار کنید |
| `503 session_superseded` | جای نشست آن اکانت توسط کلاینت دیگری گرفته شده؛ صبر کنید یا اکانت دوم اضافه کنید |
| موج 429 | اکانت بیشتر اضافه کنید (هر اکانت = یک connection) یا ترافیک را کم کنید؛ سهمیه FreeBuff روزانه ریست می‌شود |
| بعد از آپدیت ناین‌روتر مدل‌ها رفتند | `python3 freebuff9r.py status` را بزنید؛ اگر اسکیمای دیتابیس عوض شده `register` را دوباره اجرا کنید |
| خطای `bridge: token validation failed: upstream has no active session` | پراکسی **بدون پچِ** ما بیلد شده — از `install.sh` استفاده کنید (پچ `patches/0001-*.patch` را خودکار اعمال می‌کند؛ پایین را ببینید) |

## پچ‌های upstream که این ریپو حمل می‌کند

پچ‌ها در [`patches/`](patches/) هستند و `install.sh` بلافاصله بعد از clone
آن‌ها را اعمال می‌کند — idempotent: اگر قبلاً اعمال شده باشد رد می‌شود و اگر
دیگر اعمال نشود (به‌خاطر فیکس upstream) با خطای واضح متوقف می‌شود تا آپدیت
بی‌صدا خراب نشود.

### `0001-bridge-accept-idle-tokens.patch`

در upstream نسخه 1.18.2، ساخت entry در حالت bridge هر توکنی که probe آن وضعیت
سالمِ «بی‌کار» (یعنی `status: "none"`) را برگرداند رد می‌کند — در حالی که همان
کد خودش این وضعیت را معتبر و همراه `ErrNoActiveSession` مستند کرده است.
نتیجه عملی: هر اکانت FreeBuff تازه‌ای که هنوز سشنی نداشته، همه درخواست‌هایش با
`502 upstream_unavailable` شکست می‌خورد. این پچ باعث می‌شود bridge cache وضعیت
بی‌کار را بپذیرد و session manager خودش در اولین نیاز admit کند — دقیقاً
رفتاری که مسیرهای pooled خود upstream هم دارند. اگر تگ بعدی upstream این را
فیکس کند، `install.sh` صریحاً می‌گوید پچ را حذف کنید.

## همگام‌سازی لیست مدل‌ها (داشبورد ⇆ ‎/model)

لیست مدل‌هایی که pickerهای `/model` (هرمس، OpenCode و…) برای `freebuff/*` نشان
می‌دهند دقیقاً و زنده تابع همان سوییچ‌های داشبورد ناین‌روتر است
(Providers → FreeBuff):

- **نحوه کار:** سوییچ‌های تک‌تک مدل‌ها در داشبورد از روی ردیف‌های
  `customModels` رندر می‌شوند و وضعیت روشن/خاموش در `disabledModels` ذخیره
  می‌شود. `/v1/models` ناین‌روتر اجتماع کاتالوگ زنده پراکسی و این ردیف‌ها را
  **منهای** مدل‌های خاموش‌شده برمی‌گرداند — فیلتر غیرفعال روی ردیف‌های
  customModels هم اعمال می‌شود، پس مدلی که خاموش می‌کنید بلافاصله از همه
  pickerها می‌رود و روتر فعالانه با HTTP 400 ردش می‌کند.
- **`scripts/sync-models.py`** — ممیزی و ترمیم خودکار و idempotent: لیست
  سوییچ‌ها (ردیف‌های customModels) را از کاتالوگ زنده پراکسی تازه می‌کند (مدل
  جدید upstream سوییچ می‌گیرد، مدل منقضی حذف می‌شود)، ردیف‌های سرگردان
  `disabledModels` زیر کلید prefix را که فعال‌سازی مجدد در UI را بی‌اثر
  می‌کنند حذف می‌کند، و کش picker هرمس
  (`~/.hermes/provider_models_cache.json` با TTL یک‌ساعته) را باطل می‌کند تا
  تغییر بلافاصله دیده شود، نه یک ساعت بعد.
- **`scripts/sync-models-watch.py`** + سرویس
  `systemd/freebuff-model-sync.service` — وضعیت سوییچ‌ها در دیتابیس را زیر نظر
  دارد (ضدحلقه: ترافیک نوشتاری عادی ناین‌روتر و نوشته‌های idempotent خودش را
  نادیده می‌گیرد) و حدود یک ثانیه بعد از هر کلیک در داشبورد، همگام‌سازی را
  خودکار اجرا می‌کند:

```bash
sudo install -m644 systemd/freebuff-model-sync.service /etc/systemd/system/
sudo systemctl enable --now freebuff-model-sync
```

## قدردانی و لایسنس

- [freebucks-proxy](https://github.com/trefeon/freebucks-proxy) (MIT) — گیت‌وی.
- [ناین‌روتر](https://www.npmjs.com/package/9router) — روتر.
- این ریپازیتوری: MIT. وابستگی به Codebuff/FreeBuff ندارد.
