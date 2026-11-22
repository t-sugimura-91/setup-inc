"""コラム一覧を1ページ10本に分ける(何度実行しても同じ結果になる)。

使い方(setup-inc のフォルダで):
    python -I _tools/build_column_list.py

- 正本は column/index.html(1ページ目)。新しい記事は、これまでどおり
  column/index.html の <ul class="list"> の先頭に <li> を足してから、このスクリプトを実行する。
- column/index.html と column/page/N/index.html の <li> を全部集め、記事番号の新しい順に並べ直して
  10本ずつ配る。2ページ目以降は column/page/N/index.html に書き出す(1ページ目をひな形にする)。
- 各ページに、ページ送り(前へ・ページ番号・次へ)、title、canonical、og:url、rel=prev/next を付ける。
- カテゴリの絞り込みがページをまたいで効くよう、ほかのページの記事を <template> に入れておく
  (絞り込み中は全ページの記事から表示し、「すべて」に戻すとそのページの10本に戻る)。
- 記事が減ってページ数が減ったら、使わなくなった column/page/N/ を消す。
- _tools/ は GitHub Pages(Jekyll)で公開されない。
"""
import os, re, sys, shutil

PER_PAGE = 10
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COL = os.path.join(ROOT, "column")
PAGE_DIR = os.path.join(COL, "page")
BASE_URL = "https://setup-inc.com/column/"
LI_INDENT = " " * 10

CSS_MARK = "/* pager:"
CSS = """
  /* pager: 一覧のページ送り(_tools/build_column_list.py が入れる) */
  .pager{display:flex; flex-wrap:wrap; justify-content:center; align-items:center; gap:8px; margin:40px 0 0;}
  .pager[hidden]{display:none;}
  .pager a, .pager span{display:inline-flex; align-items:center; justify-content:center; min-width:44px; height:44px; padding:0 14px; border:1px solid var(--rule); border-radius:2px; font-family:var(--mono); font-size:13px; letter-spacing:.04em; color:var(--navy); text-decoration:none; background:#fff; transition:.15s ease;}
  .pager a:hover{border-color:var(--gold); color:var(--gold-deep);}
  .pager [aria-current="page"]{background:var(--navy); border-color:var(--navy); color:#fff;}
  .pager .pg-off{color:var(--rule); border-color:var(--rule);}
  .pager .pg-step{font-family:var(--sans); letter-spacing:.06em;}
  @media (max-width:420px){ .pager a, .pager span{min-width:40px; padding:0 10px;} }
"""


def read(p):
    s = open(p, encoding="utf-8", newline="").read()
    return s, ("\r\n" if "\r\n" in s else "\n")


LIST_RE = re.compile(r'(<ul class="list">)(.*?)(\n[ \t]*</ul>)', re.S)
LI_RE = re.compile(r'^([ \t]*)<li>.*?</li>', re.S | re.M)


def items_of(s, unprefix):
    """<ul class="list"> の <li> を、インデントを外した形で返す。"""
    s = s.replace("\r\n", "\n")
    m = LIST_RE.search(s)
    assert m, "<ul class=\"list\"> が見つからない"
    out = []
    for lm in LI_RE.finditer(m.group(2)):
        ind = lm.group(1)
        lines = lm.group(0)[len(ind):].split("\n")
        li = "\n".join(l[len(ind):] if l.startswith(ind) else l.lstrip(" ") for l in lines)
        if unprefix:
            li = re.sub(r'((?:href|src)=")\.\./\.\./', r"\1", li)
        out.append(li)
    return out


def key_of(li):
    return re.search(r'<a href="([^"]+)"', li).group(1)


def num_of(li):
    m = re.search(r"(\d+)/?$", key_of(li))
    return int(m.group(1)) if m else -1


def indent(li, ind):
    return "\n".join(ind + l if l else l for l in li.split("\n"))


def rel(v, prefix):
    """1ページ目(column/)基準の相対パスを、page/N/ 基準に直す。"""
    if not prefix or re.match(r"(?:[a-z]+:|/|#|\?)", v):
        return v
    if v.startswith("./"):
        v = v[2:]
    return prefix + v


def rewrite_paths(s, prefix):
    s = re.sub(r'((?:href|src)=")([^"]*)(")', lambda m: m.group(1) + rel(m.group(2), prefix) + m.group(3), s)
    s = re.sub(r'(url\(")([^"]*)("\))', lambda m: m.group(1) + rel(m.group(2), prefix) + m.group(3), s)
    return s


def page_href(k, cur):
    """ページ k へのリンク(1ページ目 column/ 基準。2ページ目以降は rewrite_paths で ../../ が付く)。"""
    return "./" if k == 1 else "page/%d/" % k


def page_url(k):
    return BASE_URL if k == 1 else BASE_URL + "page/%d/" % k


def pager_html(cur, total, ind):
    if total <= 1:
        return ""
    a = []
    if cur > 1:
        a.append('<a class="pg-step" href="%s" rel="prev">← 前へ</a>' % page_href(cur - 1, cur))
    else:
        a.append('<span class="pg-step pg-off" aria-hidden="true">← 前へ</span>')
    for k in range(1, total + 1):
        if k == cur:
            a.append('<span aria-current="page">%d</span>' % k)
        else:
            a.append('<a href="%s" aria-label="%dページ目">%d</a>' % (page_href(k, cur), k, k))
    if cur < total:
        a.append('<a class="pg-step" href="%s" rel="next">次へ →</a>' % page_href(cur + 1, cur))
    else:
        a.append('<span class="pg-step pg-off" aria-hidden="true">次へ →</span>')
    inner = "\n".join(ind + "  " + x for x in a)
    return '%s<nav class="pager" id="pager" aria-label="ページ送り">\n%s\n%s</nav>' % (ind, inner, ind)


def block(name, body, ind):
    return "%s<!-- %s:start(_tools/build_column_list.py が書く) -->\n%s%s<!-- %s:end -->" % (
        ind, name, body + "\n" if body else "", ind, name)


def build(template, pages, cur):
    s = template
    total = len(pages)
    # 一覧
    lis = "\n".join(indent(li, LI_INDENT) for li in pages[cur - 1])
    s = LIST_RE.sub(lambda m: m.group(1) + "\n" + lis + m.group(3), s, count=1)
    # 前回の生成分を外す
    s = re.sub(r"\n[ \t]*<!-- (pager|other-items):start.*?<!-- \1:end -->", "", s, flags=re.S)
    s = re.sub(r'\n<link rel="(?:prev|next)" href="[^"]*">', "", s)
    # ページ送りと、ほかのページの記事(絞り込み用)
    ind = " " * 8
    others = [li for i, p in enumerate(pages) if i != cur - 1 for li in p]
    tpl = ""
    if others:
        tpl = '%s<template id="other-items">\n%s\n%s</template>' % (
            ind, "\n".join(indent(li, LI_INDENT) for li in others), ind)
    add = "\n" + block("pager", pager_html(cur, total, ind), ind) + "\n" + block("other-items", tpl, ind)
    s = LIST_RE.sub(lambda m: m.group(0) + add, s, count=1)
    # head
    links = []
    if cur > 1:
        links.append('<link rel="prev" href="%s">' % page_url(cur - 1))
    if cur < total:
        links.append('<link rel="next" href="%s">' % page_url(cur + 1))
    s = re.sub(r'(<link rel="canonical" href=")[^"]*(">)', lambda m: m.group(1) + page_url(cur) + m.group(2) + "".join("\n" + l for l in links), s, count=1)
    s = re.sub(r'(<meta property="og:url" content=")[^"]*(">)', lambda m: m.group(1) + page_url(cur) + m.group(2), s, count=1)
    if CSS_MARK not in s:
        s = s.replace("</style>", CSS.lstrip("\n") + "</style>", 1)
    if cur > 1:
        suffix = "(%dページ目)" % cur
        s = re.sub(r"<title>コラム｜SET UP</title>", "<title>コラム%s｜SET UP</title>" % suffix, s, count=1)
        s = re.sub(r'(<meta property="og:title" content=")コラム｜SET UP(">)', r"\1コラム%s｜SET UP\2" % suffix, s, count=1)
        s = re.sub(r'(<meta (?:name|property)="(?:og:)?description" content="[^"]*?)(">)', r"\1%s\2" % suffix, s)
        s = s.replace('<p class="label">新着記事</p>', '<p class="label">新着記事 %d / %dページ</p>' % (cur, total), 1)
        s = rewrite_paths(s, "../../")
    return s


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p1 = os.path.join(COL, "index.html")
    src, nl = read(p1)
    template = src.replace("\r\n", "\n")
    found = items_of(template, False)
    if os.path.isdir(PAGE_DIR):
        for d in sorted(os.listdir(PAGE_DIR)):
            f = os.path.join(PAGE_DIR, d, "index.html")
            if d.isdigit() and os.path.isfile(f):
                found += items_of(read(f)[0], True)
    seen, items = set(), []
    for li in found:  # 同じ記事が2か所にあれば、1ページ目(先に読んだ方)を使う
        k = key_of(li)
        if k not in seen:
            seen.add(k); items.append(li)
    items.sort(key=num_of, reverse=True)
    pages = [items[i:i + PER_PAGE] for i in range(0, len(items), PER_PAGE)] or [[]]
    total = len(pages)
    for cur in range(1, total + 1):
        out = build(template, pages, cur).replace("\n", nl)
        path = p1 if cur == 1 else os.path.join(PAGE_DIR, str(cur), "index.html")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        old = open(path, encoding="utf-8", newline="").read() if os.path.isfile(path) else None
        if out != old:
            open(path, "w", encoding="utf-8", newline="").write(out)
        print("%s: %d本%s" % (os.path.relpath(path, ROOT), len(pages[cur - 1]), "" if out != old else "(変更なし)"))
    if os.path.isdir(PAGE_DIR):
        for d in os.listdir(PAGE_DIR):
            if d.isdigit() and int(d) > total:
                shutil.rmtree(os.path.join(PAGE_DIR, d)); print("削除: column/page/%s/" % d)
        if not os.listdir(PAGE_DIR):
            os.rmdir(PAGE_DIR)
    print("合計 %d本 / %dページ" % (len(items), total))


if __name__ == "__main__":
    main()
