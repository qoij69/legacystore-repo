#!/usr/bin/env python3
"""
LegacyStore repo tool: registers APKs in apps.json and checks the catalog.

  python3 tools/add_app.py add  path/to/App.apk [--name N] [--summary S] [--description D]
                                [--category C] [--changelog T] [--icon icon.png] [--prune] [--force]
  python3 tools/add_app.py list
  python3 tools/add_app.py remove com.example.app
  python3 tools/add_app.py check

`add` reads package / version / minSdk / label from the APK with aapt, copies the APK to
apks/<package>_<versionCode>.apk, computes sha256 and size and writes/updates the entry.
aapt is searched in: --aapt, $AAPT, PATH, ~/lineage14/out/host/linux-x86/bin, $ANDROID_HOME.
Without aapt pass --package --version-code --version-name (and --min-sdk) yourself.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "apps.json")


def die(msg):
    sys.exit("error: " + msg)


def load():
    if not os.path.exists(CATALOG):
        return {"version": 1, "apps": []}
    with open(CATALOG, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("version", 1)
    data.setdefault("apps", [])
    return data


def save(data):
    data["apps"].sort(key=lambda a: (a.get("name") or a["package"]).lower())
    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_aapt(explicit):
    cands = [explicit, os.environ.get("AAPT"), shutil.which("aapt"),
             os.path.expanduser("~/lineage14/out/host/linux-x86/bin/aapt")]
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if sdk:
        cands += sorted(glob.glob(os.path.join(sdk, "build-tools", "*", "aapt")), reverse=True)
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def parse_badging(text):
    info = {}
    m = re.search(r"package: name='([^']+)' versionCode='(\d+)'(?: versionName='([^']*)')?", text)
    if m:
        info["package"] = m.group(1)
        info["versionCode"] = int(m.group(2))
        info["versionName"] = m.group(3) or m.group(2)
    m = re.search(r"^sdkVersion:'(\d+)'", text, re.M)
    if m:
        info["minSdk"] = int(m.group(1))
    m = re.search(r"^application-label:'([^']*)'", text, re.M)
    if m:
        info["name"] = m.group(1)
    return info


def read_apk(apk, args):
    info = {}
    aapt = find_aapt(args.aapt)
    if aapt:
        out = subprocess.run([aapt, "dump", "badging", apk], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, universal_newlines=True)
        if out.returncode != 0:
            die("aapt could not read %s:\n%s" % (apk, out.stderr.strip()))
        info = parse_badging(out.stdout)
    if args.package:
        info["package"] = args.package
    if args.version_code is not None:
        info["versionCode"] = args.version_code
    if args.version_name:
        info["versionName"] = args.version_name
    if args.min_sdk is not None:
        info["minSdk"] = args.min_sdk
    for key in ("package", "versionCode"):
        if key not in info:
            die("could not read %s from the APK. Install aapt or pass --package --version-code "
                "--version-name" % key)
    info.setdefault("versionName", str(info["versionCode"]))
    info.setdefault("minSdk", 1)
    return info


def cmd_add(args):
    apk = os.path.abspath(args.apk)
    if not os.path.isfile(apk):
        die("no such file: " + apk)
    info = read_apk(apk, args)
    pkg, vc = info["package"], info["versionCode"]
    data = load()
    entry = next((a for a in data["apps"] if a["package"] == pkg), None)
    if entry and int(entry["versionCode"]) >= vc and not args.force:
        die("%s: catalog already has versionCode %s (new one is %s). Bump versionCode, or use "
            "--force." % (pkg, entry["versionCode"], vc))

    os.makedirs(os.path.join(ROOT, "apks"), exist_ok=True)
    rel_apk = "apks/%s_%d.apk" % (pkg, vc)
    dest = os.path.join(ROOT, rel_apk)
    if os.path.abspath(dest) != apk:
        shutil.copyfile(apk, dest)

    new = dict(entry) if entry else {}
    new["package"] = pkg
    new["name"] = args.name or new.get("name") or info.get("name") or pkg.split(".")[-1]
    new["summary"] = args.summary if args.summary is not None else new.get("summary", "")
    new["description"] = (args.description if args.description is not None
                          else new.get("description", new["summary"]))
    new["category"] = args.category if args.category is not None else new.get("category", "")
    if args.icon:
        os.makedirs(os.path.join(ROOT, "icons"), exist_ok=True)
        shutil.copyfile(args.icon, os.path.join(ROOT, "icons", pkg + ".png"))
        new["icon"] = "icons/%s.png" % pkg
    elif "icon" not in new and os.path.exists(os.path.join(ROOT, "icons", pkg + ".png")):
        new["icon"] = "icons/%s.png" % pkg
    new["versionCode"] = vc
    new["versionName"] = info["versionName"]
    new["apk"] = rel_apk
    new["sha256"] = sha256(dest)
    new["size"] = os.path.getsize(dest)
    new["minSdk"] = info["minSdk"]
    new["changelog"] = args.changelog if args.changelog is not None else ""
    if entry:
        data["apps"][data["apps"].index(entry)] = new
    else:
        data["apps"].append(new)
    save(data)

    if args.prune:
        for old in glob.glob(os.path.join(ROOT, "apks", pkg + "_*.apk")):
            if os.path.abspath(old) != os.path.abspath(dest):
                os.remove(old)
                print("removed", os.path.relpath(old, ROOT))
    print("%s %s (%s) -> %s  [%d bytes]" % ("updated" if entry else "added", pkg,
                                          new["versionName"], rel_apk, new["size"]))


def cmd_list(args):
    for a in load()["apps"]:
        print("%-32s %-10s code %-4s %s" % (a["package"], a.get("versionName", ""),
                                            a["versionCode"], a.get("name", "")))


def cmd_remove(args):
    data = load()
    keep = [a for a in data["apps"] if a["package"] != args.package]
    if len(keep) == len(data["apps"]):
        die("not in the catalog: " + args.package)
    data["apps"] = keep
    save(data)
    for f in glob.glob(os.path.join(ROOT, "apks", args.package + "_*.apk")):
        os.remove(f)
    icon = os.path.join(ROOT, "icons", args.package + ".png")
    if os.path.exists(icon):
        os.remove(icon)
    print("removed", args.package)


def cmd_check(args):
    data = load()
    problems = []
    seen = set()
    for a in data["apps"]:
        pkg = a.get("package", "?")
        if pkg in seen:
            problems.append("%s: listed twice" % pkg)
        seen.add(pkg)
        for key in ("package", "name", "versionCode", "apk"):
            if key not in a:
                problems.append("%s: missing '%s'" % (pkg, key))
        apk = a.get("apk", "")
        if apk and not apk.startswith("http"):
            p = os.path.join(ROOT, apk)
            if not os.path.isfile(p):
                problems.append("%s: file missing: %s" % (pkg, apk))
            else:
                if a.get("sha256") and sha256(p) != a["sha256"].lower():
                    problems.append("%s: sha256 does not match %s" % (pkg, apk))
                if a.get("size") and os.path.getsize(p) != a["size"]:
                    problems.append("%s: size does not match %s" % (pkg, apk))
        icon = a.get("icon", "")
        if icon and not icon.startswith("http") and not os.path.isfile(os.path.join(ROOT, icon)):
            problems.append("%s: icon missing: %s" % (pkg, icon))
    for p in problems:
        print("PROBLEM:", p)
    print("%d app(s) checked, %d problem(s)" % (len(data["apps"]), len(problems)))
    sys.exit(1 if problems else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("add")
    a.add_argument("apk")
    a.add_argument("--name")
    a.add_argument("--summary")
    a.add_argument("--description")
    a.add_argument("--category")
    a.add_argument("--changelog")
    a.add_argument("--icon", help="PNG, about 192x192")
    a.add_argument("--prune", action="store_true", help="delete older APKs of this app")
    a.add_argument("--force", action="store_true", help="allow the same or a lower versionCode")
    a.add_argument("--aapt")
    a.add_argument("--package")
    a.add_argument("--version-code", type=int)
    a.add_argument("--version-name")
    a.add_argument("--min-sdk", type=int)
    a.set_defaults(fn=cmd_add)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    r = sub.add_parser("remove")
    r.add_argument("package")
    r.set_defaults(fn=cmd_remove)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    args = ap.parse_args()
    if not getattr(args, "fn", None):
        ap.print_help()
        sys.exit(2)
    args.fn(args)


if __name__ == "__main__":
    main()
