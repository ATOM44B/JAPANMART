[README.md](https://github.com/user-attachments/files/32412995/README.md)
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
  - `HTTP 403` on every page: the site is blocking GitHub's servers. Run the robot on your own computer instead (see below).
  - `blocked by robots.txt`: the site asks robots to skip that page. The robot obeys this by default.
  - `found: 0` on pages that load: the page layout is different from what the robot expects. On your computer run
    `python scraper/scrape.py --probe "PASTE-A-LISTING-URL"` and send me the output.

**Run the robot on your own computer** (needs Python 3.10+):

```
pip install -r scraper/requirements.txt
python scraper/scrape.py
git add -A data && git commit -m "data" && git push
```

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
