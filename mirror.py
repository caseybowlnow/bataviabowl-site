#!/usr/bin/env python3
"""One-time mirror of the Lovable-built bataviabowl.com into plain static HTML.

Run by .github/workflows/mirror.yml. Produces index.html + <route>/index.html,
assets/ and images/ with relative paths so the site works on GitHub Pages
(both the github.io sub-path and the custom domain). All framework/Lovable
JavaScript is removed so the HTML is the single source of truth that the
Batavia Website Claude connector edits.
"""
import html
import os
import re
import sys
import urllib.request

ORIGIN = os.environ.get("MIRROR_ORIGIN", "https://bataviabowl.com")
ROUTES = ["/", "/parties", "/leagues", "/specials", "/menu", "/contact"]
OUT = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (BowlNow site mirror)"}

FAQ = {
    "What food and drinks are included in the party packages?":
        "Each birthday party package includes pizza and soft drinks for all participating bowlers. Additional food, snacks, and beverages are available for purchase. We also welcome parents to pre-order extra items if you're expecting adults or want to extend the celebration.",
    "Can I bring my own birthday cake or decorations?":
        "Absolutely! You are welcome to bring a birthday cake, cupcakes, or other desserts. Basic party decorations are allowed as well. Just let us know your setup plans so we can assist you and make sure everything runs smoothly.",
    "How early should we arrive before our scheduled party time?":
        "We recommend arriving 10–15 minutes before your scheduled start time. This gives you and your guests time to check in, get shoes, and settle in so your party can begin promptly and run on schedule.",
    "Can we customize our party, like adding bumpers or themed decorations?":
        "Absolutely! You can add bumpers for safe, hassle-free bowling. Birthday bowling pins with Sharpies are available for an extra fee. We're also happy to accommodate custom decorations and special requests — just specify them in the Party Request Form.",
    "How do I book a bowling birthday party in Batavia?":
        "Simply fill out our Party Request Form or give us a call. A team member will follow up to confirm your reservation. (Note: form submission is a request, not a guaranteed booking. Higher chance when you call!)",
    "Do you require a deposit to reserve a party?":
        "We currently do not require a deposit to reserve a party.",
}

FAQ_JS = """<script>
document.querySelectorAll('[data-faq] > div > button').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var item = btn.parentElement;
    var open = !item.querySelector(':scope > div').hidden;
    item.parentElement.querySelectorAll(':scope > div').forEach(function (it) {
      it.querySelector(':scope > div').hidden = true;
      it.querySelector('svg').innerHTML = '<path d="M5 12h14"></path><path d="M12 5v14"></path>';
    });
    if (!open) {
      item.querySelector(':scope > div').hidden = false;
      btn.querySelector('svg').innerHTML = '<path d="M5 12h14"></path>';
    }
  });
});
</script>"""

downloaded = {}


def get(url, binary=False):
    req = urllib.request.Request(url if url.startswith("http") else ORIGIN + url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode("utf-8")


def save(rel, data):
    path = os.path.join(OUT, rel.lstrip("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def local_asset(url):
    """Download a same-origin asset once; return its site-relative path (no leading slash)."""
    m = re.match(r"^/__l5e/assets-v1/[^/]+/(.+)$", url)
    rel = ("images/" + m.group(1)) if m else url.lstrip("/")
    if rel not in downloaded:
        save(rel, get(url, binary=True))
        downloaded[rel] = True
        print("asset", url, "->", rel)
    return rel


def fix_faq(page):
    if "lucide-plus" not in page and "lucide-minus" not in page:
        return page
    marker = '<div class="space-y-3">'
    idx = page.find(marker)
    while idx != -1:
        seg_start = idx + len(marker)
        if "<button" in page[seg_start:seg_start + 200]:
            page = page[:idx] + '<div class="space-y-3" data-faq="">' + page[seg_start:]
        idx = page.find(marker, idx + 1)

    def add_answer(m):
        btn, q = m.group(1), html.unescape(m.group(2))
        if m.group(3):  # answer already rendered (the open item)
            return m.group(0)
        ans = FAQ.get(q)
        if not ans:
            print("WARN no FAQ answer for", q, file=sys.stderr)
            return m.group(0)
        return (btn + '<div class="border-t border-neutral-200 px-5 py-4 text-neutral-700" hidden="">'
                + html.escape(ans, quote=False) + "</div></div>")

    pattern = re.compile(
        r'(<button class="flex w-full items-center justify-between[^"]*"><span>(.*?)</span>.*?</button>)'
        r'(<div class="border-t[^"]*">.*?</div>)?</div>', re.S)
    page = pattern.sub(add_answer, page)
    return page.replace("</body>", FAQ_JS + "</body>")


def transform(page, route):
    depth = 0 if route == "/" else 1
    prefix = "../" * depth

    # Strip every script (TanStack hydration, Lovable badge/analytics) and module preloads.
    page = re.sub(r"<script\b[^>]*>.*?</script>", "", page, flags=re.S)
    page = re.sub(r"<script\b[^>]*/>", "", page)
    page = re.sub(r'<link rel="modulepreload"[^>]*>', "", page)
    page = re.sub(r'<aside\s+id="lovable-badge".*?</aside>', "", page, flags=re.S)
    page = re.sub(r'content="https://[^"]*lovable\.app[^"]*\.png"', 'content="%s/images/hero-lanes.png"' % ORIGIN, page)
    page = re.sub(r"<style\b[^>]*>(?:(?!</style>).)*lovable-badge.*?</style>", "", page, flags=re.S)

    # Same-origin assets -> local files.
    def asset_sub(m):
        attr, url = m.group(1), m.group(2)
        return '%s="%s%s"' % (attr, prefix, local_asset(url))
    page = re.sub(r'(src|href)="(/(?:__l5e/assets-v1|assets)/[^"]+)"', asset_sub, page)
    page = re.sub(r'(href)="(/favicon\.ico)"', asset_sub, page)

    # Internal page links -> relative.
    def link_sub(m):
        path = m.group(1)
        if path == "/":
            return 'href="%s"' % (prefix or "./")
        return 'href="%s%s/"' % (prefix, path.strip("/"))
    page = re.sub(r'href="(/(?:parties|leagues|specials|menu|contact)?)"', link_sub, page)

    page = fix_faq(page)
    return page


def main():
    css_done = set()
    for route in ROUTES:
        raw = get(route)
        for css in re.findall(r'href="(/assets/[^"]+\.css)"', raw):
            if css in css_done:
                continue
            css_done.add(css)
            text = get(css)
            for u in re.findall(r"url\((/[^)\"']+)\)", text):
                rel = local_asset(u)
                text = text.replace("url(%s)" % u, "url(../%s)" % rel if rel.startswith("images/") else "url(%s)" % u.replace("/assets/", ""))
            save(css, text)
            print("css", css)
        page = transform(raw, route)
        out = "index.html" if route == "/" else route.strip("/") + "/index.html"
        save(out, page)
        print("page", route, "->", out, len(page))
    try:
        save("favicon.ico", get("/favicon.ico", binary=True))
    except Exception as e:  # favicon is optional
        print("favicon skipped", e)
    save(".nojekyll", "")


if __name__ == "__main__":
    main()
