"""
Diagnostic: test what HTTP caching headers LosslessBob returns.

Run from the repo root:
    python tools/test_site_headers.py

Reports whether the server supports ETag, Last-Modified, HEAD requests,
and conditional GET (304 Not Modified) — all of which determine how
efficiently we can detect page changes without re-downloading full bodies.
"""
import sys
import time
import requests

BASE    = "http://www.losslessbob.wonderingwhattochoose.com"
HEADERS = {"User-Agent": "LosslessBob-Archiver/1.0 (header diagnostic)"}

# A stable, long-existing entry page — unlikely to disappear.
TEST_URL = BASE + "/detail/LB-00001.html"
# The flat-file download page — key for site-wide change detection.
FF_URL   = BASE + "/detail/LB-bootleg-by-title.html"

SEP = "-" * 60

def print_headers(resp, label: str) -> None:
    print(f"\n  [{label}]  HTTP {resp.status_code}  {resp.url}")
    interesting = [
        "ETag", "Last-Modified", "Cache-Control", "Expires",
        "Content-Length", "Content-Type", "Vary", "Age",
        "X-Cache", "CF-Cache-Status",
    ]
    for h in interesting:
        val = resp.headers.get(h)
        if val:
            print(f"    {h}: {val}")
    if not any(resp.headers.get(h) for h in interesting):
        print("    (none of the above headers present)")


def test_url(url: str, label: str) -> dict:
    print(f"\n{SEP}")
    print(f"TARGET: {label}")
    print(f"URL:    {url}")

    result = {"etag": None, "last_modified": None, "supports_304": False}

    # 1. Normal GET
    print("\n1. GET (normal)")
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        print_headers(r, "GET")
        result["etag"]          = r.headers.get("ETag")
        result["last_modified"] = r.headers.get("Last-Modified")
        result["body_len"]      = len(r.content)
        print(f"    Body size: {len(r.content):,} bytes")
    except Exception as e:
        print(f"  ERROR: {e}")
        return result

    time.sleep(1)

    # 2. HEAD request
    print("\n2. HEAD (no body expected)")
    try:
        h = requests.head(url, headers=HEADERS, timeout=30)
        print_headers(h, "HEAD")
        cl = h.headers.get("Content-Length")
        if cl:
            print(f"    Content-Length advertised: {cl} bytes  "
                  f"({'matches' if int(cl) == result['body_len'] else 'MISMATCH vs GET body'})")
        if h.status_code == 405:
            print("    *** Server does NOT support HEAD (405 Method Not Allowed)")
        elif h.status_code == 200:
            print("    *** Server supports HEAD — good for cheap polling")
    except Exception as e:
        print(f"  ERROR: {e}")

    time.sleep(1)

    # 3. Conditional GET — If-None-Match (ETag)
    if result["etag"]:
        print(f"\n3. Conditional GET with If-None-Match: {result['etag']}")
        try:
            cr = requests.get(
                url,
                headers={**HEADERS, "If-None-Match": result["etag"]},
                timeout=30,
            )
            print_headers(cr, "conditional GET")
            if cr.status_code == 304:
                print("    *** 304 Not Modified — server honours ETag! OPTIMAL change detection.")
                result["supports_304"] = True
            elif cr.status_code == 200:
                print("    *** 200 returned (no 304) — server ignores If-None-Match.")
            else:
                print(f"    *** Unexpected status {cr.status_code}")
        except Exception as e:
            print(f"  ERROR: {e}")
        time.sleep(1)
    else:
        print("\n3. Conditional GET (ETag) — SKIPPED (no ETag in initial response)")

    # 4. Conditional GET — If-Modified-Since
    if result["last_modified"]:
        print(f"\n4. Conditional GET with If-Modified-Since: {result['last_modified']}")
        try:
            cr = requests.get(
                url,
                headers={**HEADERS, "If-Modified-Since": result["last_modified"]},
                timeout=30,
            )
            print_headers(cr, "conditional GET")
            if cr.status_code == 304:
                print("    *** 304 Not Modified — server honours If-Modified-Since! OPTIMAL.")
                result["supports_304"] = True
            elif cr.status_code == 200:
                print("    *** 200 returned — server ignores If-Modified-Since.")
            else:
                print(f"    *** Unexpected status {cr.status_code}")
        except Exception as e:
            print(f"  ERROR: {e}")
        time.sleep(1)
    else:
        print("\n4. Conditional GET (If-Modified-Since) — SKIPPED (no Last-Modified in initial response)")

    return result


def main():
    print("=" * 60)
    print("LosslessBob HTTP header diagnostic")
    print("=" * 60)

    r1 = test_url(TEST_URL, "Entry detail page (LB-00001.html)")
    time.sleep(2)
    r2 = test_url(FF_URL,   "Bootleg-by-title index page")

    print(f"\n{SEP}")
    print("SUMMARY")
    print(SEP)
    for label, r in [("Entry page", r1), ("Bootleg index", r2)]:
        has_etag = bool(r.get("etag"))
        has_lm   = bool(r.get("last_modified"))
        s304     = r.get("supports_304", False)
        print(f"  {label}:")
        print(f"    ETag present:          {'YES — ' + r['etag'] if has_etag else 'no'}")
        print(f"    Last-Modified present: {'YES — ' + r['last_modified'] if has_lm else 'no'}")
        print(f"    Server honours 304:    {'YES — conditional GET works!' if s304 else 'no (fall back to SHA256)'}")

    print(f"\n{SEP}")
    print("RECOMMENDATION")
    print(SEP)
    any_304 = r1.get("supports_304") or r2.get("supports_304")
    any_lm  = r1.get("last_modified") or r2.get("last_modified")
    any_et  = r1.get("etag") or r2.get("etag")

    if any_304:
        print("  Server supports conditional requests.")
        print("  Strategy: HEAD → conditional GET → 304 short-circuit.")
        print("  Individual pages can be polled cheaply without full body download.")
    elif any_lm or any_et:
        print("  Server returns caching headers but does not honour conditional GET.")
        print("  Strategy: HEAD → compare stored ETag/Last-Modified.")
        print("  If headers unchanged → skip. If changed (or absent) → GET + SHA256.")
    else:
        print("  Server returns no caching headers.")
        print("  Strategy: rely on flat-file download page date as site-wide change signal.")
        print("  Individual page change detection requires GET + SHA256 comparison.")
        print("  Given the site changes at most monthly, this is acceptable.")


if __name__ == "__main__":
    main()
