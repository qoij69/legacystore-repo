# legacystore-repo

Catalog and downloads for LegacyStore (the app store of the LineageOS 14 ROM).

    apps.json        the catalog the store reads
    apks/            the APK files   (apks/<package>_<versionCode>.apk)
    icons/           app icons       (icons/<package>.png, about 192x192)
    tools/add_app.py adds / updates / checks entries

The store reads `https://raw.githubusercontent.com/<user>/<repo>/main/apps.json`
(`Config.REPO_URL` in the LegacyStore source). The repo must be public.

## Publish an app or an update

    python3 tools/add_app.py add ~/path/App.apk --name "App" --summary "One line" \
        --category Tools --changelog "What changed" --icon ~/path/icon.png
    python3 tools/add_app.py check
    git add -A && git commit -m "App 1.0" && git push

Updating: build the app again with a higher `versionCode`, run `add` again (name, summary, icon
are kept; pass `--prune` to delete the old APK). The store shows the update after its next
catalog refresh. raw.githubusercontent.com caches files for about 5 minutes.

## Notes

* An update must be signed with the same key as the installed version, or Android refuses it.
* Files over 100 MB are rejected by GitHub. Put big APKs in a GitHub Release and use the full
  https URL of the asset as `"apk"` in apps.json (the checksum is still checked by the store).
* `python3 tools/add_app.py check` also runs on every push (GitHub Actions).
