from __future__ import annotations

import random
from html.parser import HTMLParser

import pytest

from app.models import Media
from app.services.markdown import ALLOWED_ATTRS, ALLOWED_TAGS, _attr_filter, render, sanitize

HASH = "a1b2c3d4e5f60718293a4b5c6d7e8f90"


def make_media(session, **kw) -> Media:
    m = Media(
        hash=kw.pop("hash", HASH), filename="x.png", kind="image", mime="image/png", width=1600, height=1000, bytes=1000, alt=kw.pop("alt", "库里的替代文字"),
        caption=kw.pop("caption", ""), color="#d9e9f9",
        variants=[{"size": 480, "w": 480, "h": 300, "bytes": 10}, {"size": 960, "w": 960, "h": 600, "bytes": 20}, {"size": 1600, "w": 1600, "h": 1000, "bytes": 30}],
    )
    session.add(m)
    session.flush()
    return m


# ---- structure ---------------------------------------------------------------------------------------------------------------
def test_headings_get_anchors_toc_and_unique_ids():
    r = render("## 为什么 复制\n\n### 细节\n\n## 为什么 复制\n\n#### 更深\n\n##### 太深不进目录")
    assert [t["id"] for t in r.toc] == ["为什么-复制", "细节", "为什么-复制-2", "更深"]
    assert [t["level"] for t in r.toc] == [2, 3, 2, 4]
    assert '<h2 id="为什么-复制">' in r.html and '<h2 id="为什么-复制-2">' in r.html


def test_a_stray_h1_in_the_body_shifts_every_heading_down_one_level():
    r = render("# 大标题\n\n## 小节\n")
    assert "<h1" not in r.html and '<h2 id="大标题">' in r.html and '<h3 id="小节">' in r.html
    assert r.toc[0]["level"] == 2


def test_callouts_have_four_kinds_and_default_titles():
    r = render("::: tip\n内容\n:::\n\n::: warn 当时的心情\n手心出汗\n:::\n\n::: love\n:::\n\n::: note\nx\n:::")
    assert 'class="callout callout--tip"><p class="callout__title">小提示</p>' in r.html
    assert 'class="callout callout--warn"><p class="callout__title">当时的心情</p>' in r.html
    assert "callout--love" in r.html and "callout--note" in r.html
    assert "::: " not in r.html


def test_code_blocks_get_a_bar_pygments_classes_and_a_copy_button():
    r = render('```python title="backup.py"\nimport sqlite3\nprint("x < y")\n```')
    assert '<span class="code__file">backup.py</span>' in r.html
    assert 'class="code__copy" type="button"' in r.html
    assert '<code class="language-python">' in r.html and 'class="kn"' in r.html
    assert "x &lt; y" in r.html and "style=" not in r.html
    assert 'data-lang="python"' in r.html
    r2 = render("```sh:deploy.sh\nls -la\n```")
    assert '<span class="code__file">deploy.sh</span>' in r2.html
    r3 = render("```\nplain\n```")
    assert '<span class="code__file">文本</span>' in r3.html and "language-text" in r3.html
    r4 = render("```nosuchlanguage\n<b>x</b>\n```")
    assert "&lt;b&gt;x&lt;/b&gt;" in r4.html and "language-nosuchlanguage" in r4.html


def test_tables_are_wrapped_and_alignment_becomes_classes():
    r = render("| a | b | c |\n|:--|:-:|--:|\n| 1 | 2 | 3 |")
    assert r.html.startswith('<div class="table-wrap"><table>') and r.html.rstrip().endswith("</table></div>")
    assert "ta-left" in r.html and "ta-center" in r.html and "ta-right" in r.html and "style=" not in r.html


def test_task_lists_footnotes_and_inline_formatting():
    r = render("- [x] 完成\n- [ ] 没完成\n\n脚注[^a]\n\n[^a]: 说明\n\n~~删~~ **粗** *斜* `代码` <kbd>Ctrl</kbd>")
    assert r.html.count('type="checkbox"') == 2 and 'disabled="disabled"' in r.html and 'checked="checked"' in r.html
    assert 'class="footnote-ref"' in r.html and 'class="footnotes"' in r.html and 'class="footnote-backref"' in r.html
    assert "<s>删</s>" in r.html and "<kbd>Ctrl</kbd>" in r.html


def test_links_external_ones_are_marked_and_all_get_rel():
    r = render("[内](/blog/x) [外](https://example.com/a) [自己](https://blog.example/b)", site_host="blog.example")
    assert 'href="/blog/x" rel="noopener noreferrer"' in r.html
    assert 'href="https://example.com/a" class="ext"' in r.html
    assert 'href="https://blog.example/b" rel' in r.html  # same host: not marked
    assert r.html.count('rel="noopener noreferrer"') == 3


def test_details_and_other_harmless_html_survive():
    r = render("<details><summary>点开</summary>\n\n里面的字\n\n</details>\n\n<mark>高亮</mark> H<sub>2</sub>O")
    assert "<details>" in r.html and "<summary>点开</summary>" in r.html and "<mark>高亮</mark>" in r.html and "<sub>2</sub>" in r.html


# ---- pictures -----------------------------------------------------------------------------------------------------------------
def test_library_picture_becomes_a_figure_with_srcset_and_size_hints(session):
    m = make_media(session)
    r = render(f'![凌晨的书桌](media:{m.id} "写代码的凌晨")', session=session)
    assert r.html.startswith('<figure class="fig"><img ')
    assert f'src="/media/{HASH}/960.webp"' in r.html
    assert f"/media/{HASH}/480.webp 480w" in r.html and f"/media/{HASH}/1600.webp 1600w" in r.html
    assert 'width="960" height="600"' in r.html and 'loading="lazy"' in r.html and 'decoding="async"' in r.html
    assert f'data-full="/media/{HASH}/1600.webp"' in r.html and 'data-color="#d9e9f9"' in r.html
    assert 'alt="凌晨的书桌"' in r.html and "<figcaption>写代码的凌晨</figcaption>" in r.html
    assert r.media_ids == [m.id]


def test_picture_by_url_and_alt_from_library(session):
    m = make_media(session, alt="库里写的")
    r = render(f"![]({'/media/' + HASH + '/1600.webp'})", session=session)
    assert 'alt="库里写的"' in r.html and r.media_ids == [m.id]


def test_polaroid_class_goes_to_the_figure(session):
    m = make_media(session)
    r = render(f"![x](media:{m.id}){{.polaroid}}", session=session)
    assert '<figure class="fig polaroid">' in r.html


def test_consecutive_pictures_become_a_gallery(session):
    m = make_media(session)
    r = render(f"![一](media:{m.id})\n![二](media:{m.id})\n![三](media:{m.id})", session=session)
    assert '<div class="gallery gallery--3">' in r.html and r.html.count('class="gallery__item"') == 3
    two = render(f"![一](media:{m.id})\n![二](media:{m.id})", session=session)
    assert "gallery--2" in two.html
    many = render("\n".join(f"![i](media:{m.id})" for _ in range(7)), session=session)
    assert "gallery--3" in many.html


def test_inline_picture_inside_text_stays_inline(session):
    m = make_media(session)
    r = render(f"看这张 ![x](media:{m.id}) 很好", session=session)
    assert "<figure" not in r.html and 'class="inline-img"' in r.html


def test_external_pictures_become_links_and_a_warning():
    r = render("![远程](https://evil.example/p.png)")
    assert "<img" not in r.html and 'class="extimg"' in r.html and "evil.example" in r.html
    assert any("外链图片" in w for w in r.warnings)


def test_missing_library_picture_is_a_placeholder_and_a_warning(session):
    r = render("![丢了](media:424242)", session=session)
    assert "img-missing" in r.html and "<img" not in r.html and r.warnings


def test_picture_without_a_database_session_cannot_be_resolved():
    r = render("![x](media:1)")
    assert "img-missing" in r.html


# ---- text, summary, reading time ---------------------------------------------------------------------------------------------
def test_plain_text_summary_and_reading_time():
    body = "先说结论：**别用 `cp`**。" + "这是一段很长的文字。" * 80 + "\n\n```python\nprint(1)\n```\n\n第二段。"
    r = render(body)
    assert r.summary.startswith("先说结论：别用 cp。") and r.summary.endswith("…") and len(r.summary) <= 121
    assert "print(1)" in r.text and "复制" not in r.text  # code is searchable, the button label is not
    assert r.word_count > 600 and r.reading_minutes >= 2
    short = render("hello world")
    assert short.reading_minutes == 1 and short.word_count == 2


def test_summary_skips_headings_and_quotes_and_uses_the_first_paragraphs():
    r = render("## 小节\n\n> 引用不算\n\n第一段。\n\n第二段。")
    assert r.summary == "第一段。 第二段。"


def test_empty_document():
    r = render("")
    assert r.html == "" and r.toc == [] and r.summary == "" and r.word_count == 0 and r.reading_minutes == 1


def test_moment_profile_is_short_text_only():
    r = render("# 不是标题\n\n| a |\n|---|\n| b |\n\n![x](y.png)\n\n<b>raw</b> **粗**\n行二 #tag", profile="moment")
    assert "<h1" not in r.html and "<table" not in r.html and "<img" not in r.html and "<b>" not in r.html
    assert "&lt;b&gt;raw&lt;/b&gt;" in r.html and "<strong>粗</strong>" in r.html and "<br>" in r.html


# ---- XSS: nothing outside the allow-list may come out ---------------------------------------------------------------------------
class _Checker(HTMLParser):
    """Closed-world check of sanitised output: every tag, attribute and value must be on the allow-list."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self.problems.append(f"tag <{tag}>")
        allowed = ALLOWED_ATTRS["*"] | ALLOWED_ATTRS.get(tag, set()) | {"rel"}
        names = []
        for name, value in attrs:
            names.append(name)
            if name not in allowed:
                self.problems.append(f"attribute {name} on <{tag}>")
            elif name != "rel" and _attr_filter(tag, name, value or "") is None and name not in ("checked", "disabled", "open"):
                self.problems.append(f"value {name}={value!r} on <{tag}>")
            if name.startswith("on") or name in ("style", "target", "formaction", "action", "srcdoc"):
                self.problems.append(f"dangerous attribute {name}")
        if tag == "a" and "href" in names and "rel" not in names:
            self.problems.append("link without rel")
        if tag == "img" and "src" not in names:
            self.problems.append("img without src")

    handle_startendtag = handle_starttag


def assert_clean(html: str) -> None:
    checker = _Checker()
    checker.feed(html)
    checker.close()
    assert not checker.problems, (checker.problems, html)


PAYLOADS = [
    "<script>alert(1)</script>", "<SCRIPT SRC=//evil.example/x.js></SCRIPT>", "<img src=x onerror=alert(1)>", "<img src=\"x\" onerror=\"alert(1)\">",
    "<svg onload=alert(1)>", "<svg><script>alert(1)</script></svg>", "<a href=\"javascript:alert(1)\">x</a>", "[x](javascript:alert(1))",
    "[x](JaVaScRiPt:alert(1))", "[x](&#106;avascript:alert(1))", "<a href=\"jav&#x09;ascript:alert(1)\">x</a>", "<a href=\" javascript:alert(1)\">x</a>",
    "<a href=\"\x01javascript:alert(1)\">x</a>", "<a href=\"vbscript:msgbox(1)\">x</a>", "[x](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)",
    "<a href=\"data:text/html,<script>alert(1)</script>\">x</a>", "<iframe src=\"https://evil.example\"></iframe>", "<iframe srcdoc=\"<script>alert(1)</script>\"></iframe>",
    "<object data=x></object><embed src=x>", "<form action=\"https://evil.example\"><input type=submit value=go></form>", "<button formaction=\"https://evil.example\">x</button>",
    "<style>body{display:none}</style>", "<link rel=stylesheet href=//evil.example/x.css>", "<meta http-equiv=\"refresh\" content=\"0;url=https://evil.example\">",
    "<base href=\"https://evil.example/\">", "<div style=\"position:fixed;inset:0;background:red\">x</div>", "<div onclick=\"alert(1)\">x</div>",
    "<p onmouseover=alert(1)>x</p>", "<math><mtext><table><mglyph><style><!--</style><img title=\"--&gt;&lt;img src=1 onerror=alert(1)&gt;\">",
    "<noscript><p title=\"</noscript><img src=x onerror=alert(1)>\">", "<svg><style><img src=x onerror=alert(1)></style></svg>", "<a href=\"https://x\" target=\"_blank\">x</a>",
    "<input type=\"text\" autofocus onfocus=alert(1)>", "<img src=\"https://evil.example/pixel.png\">", "<img srcset=\"https://evil.example/p.png 1x\">",
    "<img src=\"/media/../../etc/passwd\">", "<img src=\"//evil.example/x.png\">", "<h2 id=\"location\">x</h2>", "<a id=\"__proto__\">x</a>", "<p class=\"unknown evil\">x</p>",
    "<xmp><script>alert(1)</script></xmp>", "<template><script>alert(1)</script></template>", "<textarea><script>alert(1)</script></textarea>",
    "<video src=x onerror=alert(1)></video>", "<audio src=x onerror=alert(1)></audio>", "<details open ontoggle=alert(1)>x</details>",
    "<!-- <script>alert(1)</script> -->", "<![CDATA[<script>alert(1)</script>]]>", "<?php echo 1; ?>", "<a href=\"#\" ONCLICK=alert(1)>x</a>",
    "<img src=x:alert(1) onerror=eval(src)>", "<body onload=alert(1)>", "<marquee onstart=alert(1)>x</marquee>", "<isindex action=javascript:alert(1)>",
    "<table background=\"javascript:alert(1)\"><tr><td>x</td></tr></table>", "<div data-x=\"1\" data-full=\"https://evil.example/\">x</div>",
    "<img data-full=\"javascript:alert(1)\" data-color=\"red;background:url(x)\" src=\"/media/a/960.webp\">", "<a href=\"//evil.example\">x</a>",
    "`<script>alert(1)</script>`", "```html\n<script>alert(1)</script>\n```", "```\"onmouseover=\"alert(1)\n```", "```x\"><script>alert(1)</script>\n```",
    "![x](\"onerror=\"alert(1))", "![\"><script>alert(1)</script>](/media/abcdef0123456789/960.webp)", "[\"><img src=x onerror=alert(1)>](/x)",
    "::: <script>alert(1)</script>\nx\n:::", "::: tip \"><img src=x onerror=alert(1)>\nx\n:::", "<br/><br/><img/src=x/onerror=alert(1)>", "<a href=javascript&colon;alert(1)>x</a>",
    "<img src=`x` onerror=alert(1)>", "<scr<script>ipt>alert(1)</scr</script>ipt>", "<<script>alert(1);//<</script>", "<svg/onload=alert(1)>",
    "<math href=\"javascript:alert(1)\">x</math>", "<a href=\"https://x\" rel=\"opener\">x</a>", "<button type=submit name=x>x</button>", "<input type=image src=x onerror=alert(1)>",
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_xss_payload_is_neutralised(payload):
    for profile in ("post", "moment"):
        html = render(payload, profile=profile).html
        assert_clean(html)  # closed-world: only allow-listed tags, attributes and values
        assert "<script" not in html.lower()
    assert_clean(sanitize(payload))


def test_dangerous_text_in_code_is_shown_not_run():
    html = render("`<script>alert(1)</script>`\n\n```html\n<img src=x onerror=alert(1)>\n```").html
    assert "<script" not in html and "&lt;script&gt;" in html and "&lt;" in html
    assert_clean(html)


def test_fuzz_random_mixtures_never_escape_the_allow_list():
    rnd = random.Random(20261022)
    atoms = PAYLOADS + ["**粗**", "# 标题", "- 列表", "> 引用", "| a | b |\n|---|---|\n| 1 | 2 |", "[链接](/x \"t\")", "<b>", "</p>", "</div></div>", "\x00", "‮", "&amp;lt;script&amp;gt;",
                        "<a href=\"", "\">", "' onerror='", "<img ", "src=x ", ">", "<!--", "-->", "```", "~~~", ":::", "[^1]", "[^1]: n", "{.polaroid}", "![](media:1)", "![](/media/0123456789abcdef/960.webp)"]
    for _ in range(1500):
        doc = rnd.choice(["", "\n", " ", "\n\n"]).join(rnd.choice(atoms) for _ in range(rnd.randint(1, 9)))
        for profile in ("post", "moment"):
            assert_clean(render(doc, profile=profile).html)


def test_sanitizer_is_idempotent_on_its_own_output(session):
    m = make_media(session)
    doc = f"## 标题\n\n::: tip\n内容\n:::\n\n![x](media:{m.id} \"图注\")\n\n```py title=a.py\nprint(1)\n```\n\n| a |\n|---|\n| 1 |\n\n- [x] t\n\n脚注[^1]\n\n[^1]: n"
    once = render(doc, session=session).html
    assert sanitize(once) == once
