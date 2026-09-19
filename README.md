# JAPANMART on GitHub: step-by-step

JAPANMART is a phone web app. Hosting it on GitHub Pages gives you a link like `https://YOUR-NAME.github.io/JAPANMART/`
that works in Safari, and a robot that refreshes the listings every 3 hours by itself. It is free.

Use a computer for the setup (about 10 minutes). Afterwards you only need your phone.

## What is in this folder

| File | What it does |
| --- | --- |
| `index.html` | The app |
| `data/products.json` | The listings the app shows. The robot rewrites it every 3 hours |
| `data/th_comps.csv` | Thai secondhand prices you log. They replace the estimate for that model |
| `scraper/scrape.py`, `config.json`, `requirements.txt` | The robot that reads Komehyo and Netmall |
| `scraper/embed.py` | Bakes the data into the page when it is published, so listings are there the moment the page opens |
| `run-on-my-computer.bat` / `.command` | One double-click to fetch Netmall from your own computer (see the section on refusals) |
| `telegram/worker.js` | The small helper that delivers Share messages through your Telegram bot (setup below) |
| `telegram/setup.html` | A guided page for setup step C (open it on your computer) |
| `telegram/test_worker.mjs` | Optional offline test for the helper (`node telegram/test_worker.mjs`) |
| `icons/`, `manifest.webmanifest` | The Home Screen icon (a black and white torii gate) in every size iPhone, iPad and Android ask for |
| `data/app.json` | Where you enter the bot name and helper address once |
| `scraper/test_scrape.py` | Optional offline test |
| `update-data.yml` | The schedule. It goes into `.github/workflows/` (step 4) |

## Setup

**1. Create a GitHub account** at github.com if you do not have one.

**2. Create the repository.** Click **+ > New repository**. Name it `JAPANMART`. Choose **Public** (free Pages needs it).
Leave every checkbox empty and click **Create repository**.

**3. Upload the app and data.** On the empty repository page click **uploading an existing file**.
Drag in `index.html`, `README.md`, and the folders `data` and `scraper` from this folder. Click **Commit changes**.
Check that the repository now shows `data/` and `scraper/` folders. (Do not upload `update-data.yml` here.)

**4. Add the schedule file.** Click **Add file > Create new file**. In the name box type exactly
`.github/workflows/update-data.yml` (typing the slashes creates the folders). Open `update-data.yml` from this folder,
copy everything, paste it into the big box, and click **Commit changes**.

**5. Turn on Pages (do not skip).** Go to **Settings > Pages**. Under **Build and deployment**, open the **Source** dropdown and choose
**GitHub Actions**. If this is not set, the run stops with "Get Pages site failed" or "HttpError: Not Found".
The repository must be **Public** on a free account.

**6. Run it once.** Open the **Actions** tab. If you see a green button that enables workflows, click it.
Click **Update data and deploy** on the left, then **Run workflow > Run workflow**. Wait 3 to 6 minutes for a green check.

**7. Open your app.** Go to **Settings > Pages**. Your link is shown at the top, for example `https://YOUR-NAME.github.io/JAPANMART/`.
On iPhone open it in Safari, tap Share, then **Add to Home Screen**.

From now on the robot runs every 3 hours, saves new data, and redeploys. The app also checks for new data whenever you open it,
every 10 minutes while it stays open, and when you tap **Refresh** under the search bar.

## Nothing to upload by hand

Every run does two things with the data: it saves `data/products.json` in the repository, and it **bakes the same data into the published page**.
Opening your link therefore shows the listings at once, even with a weak signal. While the page stays open it also checks for newer data by itself.
The **Import data file** button in the app is only for offline use and is never needed on your live link.

If the app shows "No listings yet", the robot did not find any listings. Open
`https://YOUR-NAME.github.io/JAPANMART/data/scrape_status.json` in Safari and read `message` and the `note` fields (see "Check that the data is real" below).

## If a run shows a red cross

The workflow has two jobs. **update** reads the sites and saves the data. **deploy** publishes the site.

| Message | What to do |
| --- | --- |
| `GitHub Pages is not turned on`, `Get Pages site failed`, or `HttpError: Not Found` | Settings > Pages > Source > **GitHub Actions**. Then start a new run: **Actions > Update data and deploy > Run workflow**. The data from the **update** job is already saved. |
| `GitHub Pages source is wrong` | The Source dropdown says something else. Change it to **GitHub Actions** and run again. |
| `Process completed with exit code 1` on the **update** job | Open the job and look for the step with the red cross. Most often it is **Save refreshed data**, with a line like `rejected ... fetch first`. That happens when an old run is repeated with **Re-run all jobs**: the repeat starts from an outdated copy of the repository. Use **Run workflow** for a fresh run instead. The current workflow also repairs this by itself (it refreshes and retries the save). If the red step is **Check the upload is complete**, a file is missing: `index.html`, `data/` and `scraper/` must sit at the top level of the repository, not inside another folder. |
| `Node.js 20 is deprecated` | Only a warning. This version of the workflow already uses the newer actions (checkout v7, setup-python v7, upload-pages-artifact v5, deploy-pages v5). If you still see it, replace your `.github/workflows/update-data.yml` with the one in this folder. |
| `ubuntu-latest will migrate to Ubuntu 26` | A notice, not an error. The workflow uses `ubuntu-24.04`, so it does not apply. |

To update the workflow in your repository: open `.github/workflows/update-data.yml` on GitHub, click the pencil icon, replace everything with the
contents of `update-data.yml` from this folder, and click **Commit changes**.

## Check that the data is real

Open `data/scrape_status.json` in your repository.

- `"ok": true` and a listing count above zero: all good. Photos and direct links come from the listings.
- `"ok": false`: the previous data was kept. Read `message` and the `note` on each entry in `queries`:
  - `HTTP 403` or `HTTP 500` on every page: the site refuses GitHub's servers. See the next section.
  - `blocked by robots.txt`: the site asks robots to skip that page. The robot obeys this by default.
  - `found: 0` on pages that load: the page layout is different from what the robot expects. On your computer run
    `python scraper/scrape.py --probe "PASTE-A-LISTING-URL"` and send me the output.

## Home Screen icon (iPhone)

The page now points to a proper icon (`icons/apple-touch-icon.png`, 180 x 180, black with a white torii gate), so **Add to Home Screen** shows the JAPANMART icon
instead of a screenshot of the page. iPhone rounds the corners itself.

1. Upload the `icons` folder and `manifest.webmanifest`, and replace `index.html` and `.github/workflows/update-data.yml` in your repository
   (the workflow now publishes the icons). Run the workflow.
2. On the iPhone, **delete the old JAPANMART icon** from the Home Screen (iPhone keeps the icon it saw when it was added).
3. Open your address in Safari, tap **Share** > **Add to Home Screen**. The name is proposed as JAPANMART. Tap **Add**.

To use your own artwork: replace `icons/apple-touch-icon.png` with a 180 x 180 PNG that has **no transparency** (iPhone paints transparent areas black)
and keep important parts about 10% away from the edges. Replace `icon-192.png` and `icon-512.png` too if you want the same picture on Android.

## If Netmall or Komehyo refuse GitHub (HTTP 403 or 500)

GitHub runs the robot on servers in US data centers, and Japanese shops often refuse those. This is not a mistake in your setup:
`data/scrape_status.json` may show `403` for every Netmall page and `500` for every Komehyo page. When that happens the robot changes nothing
and keeps the last good data.

The workflow already tries, in order: a plain fetch that looks like a normal browser, then a retry with a real headless browser.
It stops after 3 refused requests per site, so it does not keep knocking. `scrape_status.json` now has a `refused_by` block with the
server name and the start of the reply, which shows who is refusing. If both attempts fail, use your own internet connection instead:

**Option A: fetch Netmall on your computer and upload the result (no Git needed).**
1. Install Python 3.10 or newer from python.org. On Windows tick "Add python.exe to PATH".
2. In your repository click **Code > Download ZIP** and unzip it (this gives you the newest data and the scripts).
3. Double-click **`run-on-my-computer.bat`** (Windows) or **`run-on-my-computer.command`** (Mac; the first time right-click > Open).
   It fetches only Netmall, which takes about 5 minutes, and leaves the other shops' data as they are.
4. In your repository open the `data` folder, click **Add file > Upload files**, drop in the new `products.json` and `scrape_status.json`, and commit.
   The workflow starts by itself and publishes it.
5. Repeat whenever you want fresh Netmall listings, for example once a day. In between, GitHub's own runs keep showing the Netmall listings you
   uploaded for up to 14 days (`carry_days` in `scraper/config.json`). The line under the search bar then says "Not refreshed: Netmall (from DATE)".

**Option B: fully automatic, using your own computer as the runner.**
1. Repository **Settings > Actions > Runners > New self-hosted runner**. Follow the steps on that page on your computer and start the runner.
   The computer needs Python and Git installed (on Windows, Git for Windows).
2. **Settings > Secrets and variables > Actions > Variables > New repository variable**. Name `SCRAPER_RUNNER`, value `self-hosted`.
3. From now on the fetch job runs on your computer whenever it is on and the runner is running, using your home connection.
   Delete the variable to go back to GitHub's servers.

## Where the listings come from

| Shop | What is collected | How |
| --- | --- | --- |
| **Netmall** (Hard Off) | Earphones and headphones, audio players, speakers, cameras, lenses. About 90 searches across 22 brands (Sony, Bose, Denon, Onkyo, Pioneer, Audio-Technica, Sennheiser, Shure, JBL, Marantz, Yamaha, Teac, Technics and more) | Search result pages |
| **e☆イヤホン** (e-earphone.jp) | Used earphones, headphones, players and speakers. The robot reads the shop's own used page (`/pages/used-top`) to find the categories, then each category's product feed, which includes photos and stock | Shopify product feed, with the normal page as backup |
| **Komehyo** | Watches, bags, rings, cameras, lenses | Category pages |

The price of the same model from all shops is pooled to find its typical used price, so a cheap listing on any shop stands out.
No shop can fill the app: `source_caps` in `scraper/config.json` limits each shop (default Netmall 600, e☆イヤホン 300, Komehyo 350). When a shop is over its
limit the best deals are kept. `max_items` on a search limits how much one search adds.

In the app, the filter icon next to the budget button chooses one shop only. The line under the search bar shows how many listings each shop contributes.
If Netmall shows far fewer listings than expected, open `data/scrape_status.json` and look at `sites.netmall` (`ok` and `failed`) and `refused_by`.
Netmall refusing GitHub's servers (403) is the usual reason. See "If Komehyo and Netmall refuse GitHub".

## Share to Telegram

The **Share** button under the heart on every card sends a product to your own Telegram, ready to copy and post for sale:
1. all the photos (as an album, up to 10), then one text message with
2. product name, 3. description and condition, 4. price in Thai baht (the **Suggested** price; change it in **Assumptions > Share to Telegram > Price to post**).

The first tap opens Telegram so you can tap **Start** on the bot "JAPANMART Market Test". After that, every tap sends straight away.
A bot cannot hold its password inside a web page, so a small free helper (Cloudflare Worker) sits in between. One-time setup, about 15 minutes:

**A. Create the bot** (in Telegram)
1. Open **@BotFather**, send `/newbot`.
2. Name: `JAPANMART Market Test`. Username: something free that ends in `bot`, for example `japanmart_market_test_bot`.
3. Copy the token BotFather gives you. Keep it private: never put it in GitHub or in a chat.

**B. Create the helper** (free account at dash.cloudflare.com)
1. **Storage & Databases > KV > Create a namespace**, name it `japanmart-links`.
2. **Workers & Pages > Create > Create Worker**, name it `japanmart-telegram`, **Deploy**, then **Edit code**, replace everything with the contents of `telegram/worker.js`, **Deploy**.
3. In the Worker open **Settings > Bindings > Add > KV namespace**: variable name `LINKS`, pick `japanmart-links`.
4. **Settings > Variables and Secrets > Add**:
   `BOT_TOKEN` (type Secret) = the token from step A3.
   `WEBHOOK_SECRET` (type Secret) = any long random text using only letters, digits, `_` and `-`.
   `ALLOWED_ORIGIN` (type Text) = `https://atom44b.github.io` (your site address, no slash at the end).
5. Note the Worker address, like `https://japanmart-telegram.YOURNAME.workers.dev`. Opening it should show "JAPANMART Telegram helper is running."

**C. Point Telegram at the helper** (once). The easy way: on your computer, double-click **`telegram/setup.html`** from the downloaded folder.
Paste the bot token, the Worker address and the webhook secret, then press **1. Check the token** and **2. Connect Telegram to the helper**.
It cleans up common paste mistakes and explains any error. Nothing you type is saved or sent anywhere except to Telegram.

By hand instead: first check the token alone by pasting `https://api.telegram.org/botTHE_TOKEN/getMe` into a browser (no spaces, no `< >`, no quotes,
the word `bot` directly followed by the token). It must show `"ok":true` and your bot's name. If it shows `404 Not Found`, the token text is wrong:
copy it again from BotFather (send `/token` to get it again). Then use
`https://api.telegram.org/botTHE_TOKEN/setWebhook?url=https://japanmart-telegram.YOURNAME.workers.dev/webhook&secret_token=YOUR_WEBHOOK_SECRET`
and the reply must contain `"ok":true`.

**D. Tell the app** Edit `data/app.json` on GitHub:
`{ "telegramBot": "japanmart_market_test_bot", "telegramApi": "https://japanmart-telegram.YOURNAME.workers.dev" }`
Also replace `.github/workflows/update-data.yml` with the new `update-data.yml`, which publishes `data/app.json`. Then run the workflow.

**E. Use it.** Tap Share on a product, tap **Start** in Telegram, return to the app. Tap Share again any time. Send `/stop` to the bot to disconnect.

**If the app says "Not connected yet" after you tapped Start:**
1. Look in Telegram. After **Start** the bot must reply "✅ Connected to JAPANMART". If it stays silent, Telegram is not reaching the helper.
   Open the Worker address followed by `/diag` in a browser. `webhook.url` must be your Worker address plus `/webhook` (if it is empty, run
   `telegram/setup.html` step 2 again). `webhook.last_error` says why Telegram fails: `403` means `WEBHOOK_SECRET` in Cloudflare differs from the one you
   gave in step C, `500` means the KV binding `LINKS` is missing. Opening the plain Worker address also lists which settings are missing.
2. If the bot did reply but the app still says not connected, the app cannot read the answer. `ALLOWED_ORIGIN` in Cloudflare must be exactly your site
   address, `https://atom44b.github.io` (no slash at the end, no `/JAPANMART`), and `telegramApi` in `data/app.json` must be the Worker address.
   The app now names the exact value in its message.
3. Still nothing: in the Connect sheet tap **Copy this message**, paste it into the bot chat and send it.

Whenever you change `telegram/worker.js`: in Cloudflare open the Worker, **Edit code**, paste the new file, **Deploy**.
For anything else open the Worker's **Logs** in Cloudflare.
Shops sometimes refuse Telegram fetching a photo. The helper then downloads it itself, and if that fails the text still arrives.
The helper stores only a random connection code and your chat number. It sends nothing except what you share.

**Please note:** the photos and descriptions belong to Komehyo, Netmall and e☆イヤホン, and the item is not yours until you buy it.
Use the photos to plan and check, and post your own photos and wording once the item has arrived.

### Focus brands and Mercari

`focus_brands` in `scraper/config.json` lists the brands you care most about (Sony, Bose, Denon, Bowers & Wilkins, Bang & Olufsen, Pioneer, Onkyo,
Sennheiser, Astell & Kern). They have their own Netmall searches with a bigger share, and when a shop is over its limit their listings are kept first.

**Mercari is not a data source** and the robot never reads it. Mercari's site is built so that a plain robot sees an empty page, it limits access from
overseas, and its terms decide what automated collection is allowed. I could not read those terms myself, so please read them before anyone builds a collector.
Instead, every card's **Thai listings** button now opens a **Market check** sheet with three Mercari links for that model: for sale (cheapest first),
for sale (newest first), and **sold**. Sold prices show what a model really fetches in Japan, which is the best number for a resale decision.
Check them by hand for the items you seriously consider.

## Photos

The robot takes the photo from each listing card, whatever the page calls it (lazy-load names vary), and for items whose card has none it opens
the product page and reads the share image there. It also opens product pages of the best-looking deals to collect several photos for the carousel
(up to `detail_pages` per run in `scraper/config.json`, default 80). Photos found earlier are reused, not fetched again.

In the app, a photo that will not load directly is retried once through the free image service `images.weserv.nl`, which fetches it without a
referrer and shrinks it. That service sees the address of the photo. If it fails too, the card shows a note "Photo not available here. Open the listing"
that opens the original listing. Nothing is copied or stored.

To see how well it works: **Data** in the app says "N listings, M with photos", and `data/scrape_status.json` has a `photos` block
(`listings_without_photo`, `from_product_pages`, `examples_without_photo`). If many listings have no photo, run on your computer
`python scraper/scrape.py --probe "PASTE-A-LISTING-PAGE-URL"`. It prints the raw markup of a card that has no photo. Send me that output.

## Add real Thai secondhand prices

Profit in JAPANMART is measured against the price a **used** item sells for in Thailand. New retail prices are never used.
Until you log real listings, JAPANMART estimates it as: typical Japan used price of that model x a factor (set in the app under
**Assumptions > Thai used-market price**). Real Thai listings are better:

1. In the app open a card, tap **Thai listings**, and use the Shopee, Facebook Marketplace, Lazada and Google links.
2. Note the price of similar **used** items.
3. Add a row to `data/th_comps.csv` on GitHub (open the file, click the pencil icon):
   `model_key,source,status,thb,url,note` for example `WH-1000XM4,Facebook Marketplace,Sold,5200,https://...,good condition`.
4. Commit. The next run picks it up. Three or more rows for one model replace the estimate.

The app's **Log a Thai listing** button does the same on one device only.

## Good to know

- Screenshots: the preview inside the Claude app blocks outside links and photos. Always test with your GitHub Pages link in Safari.
- To change how often it updates, edit the `cron` line in `.github/workflows/update-data.yml`.
  GitHub can start scheduled runs a few minutes late. If the repository is quiet for a long time GitHub may pause the schedule; open the Actions tab and re-enable it.
- The robot reads public listing pages politely (2 seconds between requests) and respects robots.txt. Check each site's terms before using it heavily.
- Photos are loaded from the source sites. They are not copied or republished.
