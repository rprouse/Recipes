#!/usr/bin/env python
"""Extract a schema.org/Recipe from a page's JSON-LD into clean JSON.

The fallback path for sites that block Defuddle or render the recipe only in
JavaScript (Serious Eats and the rest of the Dotdash Meredith family —
Simply Recipes, AllRecipes, Food & Wine — are the common cases). Most recipe
sites still embed a full `<script type="application/ld+json">` Recipe block for
SEO, exactly like NYT, so a plain curl + this parser gets everything.

Usage:
    curl -sSL -A "Mozilla/5.0" "<recipe url>" -o page.html
    python parse_jsonld.py page.html out.json

Writes out.json with: name, author, yield, prep/cook/total (human text),
desc, ingredients[], steps[], image, keywords. All HTML entities are decoded
(&#39; -> ', &amp; -> &) and instruction sections are flattened recursively.
Prints a short summary to stdout. Exit 1 if no Recipe block is found (usually a
truncated/transient fetch — just retry the curl).
"""
import re, json, sys, html as htmllib


def find_recipe(html):
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        cands = data if isinstance(data, list) else (data.get('@graph') if isinstance(data, dict) and '@graph' in data else [data])
        for c in cands:
            if not isinstance(c, dict):
                continue
            t = c.get('@type')
            if 'Recipe' in (t if isinstance(t, list) else [t]):
                return c
    return None


def clean(s):
    return htmllib.unescape(s).strip() if isinstance(s, str) else s


def flat(insts):
    out = []
    for s in insts or []:
        if isinstance(s, dict):
            if s.get('@type') == 'HowToSection':
                out += flat(s.get('itemListElement', []))
            else:
                txt = clean(s.get('text', ''))
                if txt:
                    out.append(txt)
        else:
            out.append(clean(str(s)))
    return out


def iso_time(t):
    if not t:
        return ''
    if isinstance(t, list):
        t = t[0] if t else ''
    if isinstance(t, dict):
        # Some sites emit a QuantitativeValue instead of an ISO-8601 string.
        val, unit = t.get('value'), (t.get('unitText') or t.get('unitCode') or '')
        if val:
            u = str(unit).lower()
            if 'hour' in u or u in ('h', 'hur'):
                return f"{val} hour" + ("s" if str(val) not in ('1', '1.0') else "")
            return f"{val} minutes"
        t = t.get('@value') or t.get('text') or ''
    if not isinstance(t, str):
        return ''
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?', t)
    if not m:
        return ''
    h, mi = m.group(1), m.group(2)
    parts = []
    if h and int(h):
        parts.append(f"{int(h)} hour" + ("s" if int(h) > 1 else ""))
    if mi and int(mi):
        parts.append(f"{int(mi)} minutes")
    return ' '.join(parts)


def main():
    html = open(sys.argv[1], encoding='utf-8').read()
    r = find_recipe(html)
    if r is None:
        sys.exit("No schema.org/Recipe JSON-LD found — likely a truncated fetch; retry the curl.")

    auth = r.get('author')
    if isinstance(auth, list):
        auth = ', '.join(a.get('name', '') for a in auth if isinstance(a, dict))
    elif isinstance(auth, dict):
        auth = auth.get('name')

    img = r.get('image')
    if isinstance(img, dict):
        img = img.get('url')
    elif isinstance(img, list) and img:
        img = img[0].get('url') if isinstance(img[0], dict) else img[0]

    out = {
        'name': clean(r.get('name')),
        'author': clean(auth),
        'yield': r.get('recipeYield'),
        'prep': iso_time(r.get('prepTime')),
        'cook': iso_time(r.get('cookTime')),
        'total': iso_time(r.get('totalTime')),
        'desc': clean(r.get('description') or ''),
        'ingredients': [clean(i) for i in r.get('recipeIngredient', [])],
        'steps': flat(r.get('recipeInstructions', [])),
        'image': img,
        'keywords': r.get('keywords'),
    }
    json.dump(out, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('name:', out['name'])
    print('author:', out['author'])
    print('yield:', out['yield'], '| total:', out['total'], '| prep:', out['prep'], '| cook:', out['cook'])
    print('image:', out['image'])
    print('ingredients:', len(out['ingredients']), '| steps:', len(out['steps']))


if __name__ == '__main__':
    main()
