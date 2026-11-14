# Daily live jobs feed

The GitHub Actions workflow refreshes `jobs-feed.json` every day at 9:00 AM India Standard Time and publishes the updated static feed through the existing Netlify GitHub integration. You can also run it from GitHub → **Actions** → **Refresh live forensic and cybersecurity jobs** → **Run workflow**.

## India-specific listings

The importer uses the public Himalayas remote-jobs API plus Jobicy and Remote OK feeds, and can also use Jooble's India search API when configured. It filters for forensic/cybersecurity roles, India locations, or explicitly worldwide/anywhere roles; it does not assume that an unspecified remote job is open to India. Each listing includes source credit and the allowed application URL.

To add Jooble as another India source (optional):

1. Create an API key from the India Jooble API page: <https://in.jooble.org/api/about>.
2. In the GitHub repository, open **Settings → Secrets and variables → Actions → New repository secret**.
3. Name the secret `JOOBLE_API_KEY` and paste the key as its value.
4. Run the workflow once from the **Actions** tab to populate the first feed.

Keep the key in GitHub Secrets; do not add it to the website or commit it. The importer currently runs seven India search queries per refresh. Job counts depend on source availability and relevance; the site reports the verified count and never fills the target with invented listings. At least 25 cannot be guaranteed on days when the sources publish fewer qualifying openings.
