# -*- coding: utf-8 -*-
"""data/links.json + data/images.json → index.html (GitHub Pages 게시용)"""
import json
import os
import zipfile

TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>일일 정치 주요뉴스 {date_label}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header>
  <h1>일일 정치 주요뉴스</h1>
  <p class="date">{date_label} · 기준 {window_start} ~ {window_end}</p>
  <p class="download">
    <a href="output/latest.xlsx">엑셀 다운로드</a>
    <button id="refresh-btn" class="refresh-btn" type="button">🔄 지금 업데이트</button>
  </p>
  <p id="refresh-note" class="hint" hidden></p>
</header>

<section class="infographics">
  <h2>📊 인포그래픽·차트 ({infographic_count}건)</h2>
  <p class="hint">"이미지 다운로드"를 누르거나, 이미지를 길게 눌러 저장한 뒤 카톡으로 보내세요.</p>
  <div class="gallery">
    {infographics_html}
  </div>
</section>

<section class="project1">
  <h2>프로젝트1 — 정치·정당·경제 주요기사</h2>
  <button class="copy-btn copy-all" data-copy-target="copy-all-text" type="button">📋 전체 복사 (카톡용)</button>
  {sectors_html}
</section>

<section class="project2">
  <div class="section-head">
    <h2>프로젝트2 — 네이버 메인 뉴스 캡쳐 ({image_count}건)</h2>
    <a class="zip-btn" href="output/images.zip">📦 이미지 전체 일괄 다운로드 ({total_image_count}장)</a>
  </div>
  <p class="hint">"이미지 다운로드"를 누르거나, 이미지를 길게 눌러 저장한 뒤 카톡으로 보내세요.</p>
  <div class="gallery">
    {gallery_html}
  </div>
</section>

<footer>
  <p>자동 생성 · Daily Morning News · 매일 GitHub Actions로 갱신</p>
</footer>

<div id="copy-toast" class="toast" hidden>복사됨!</div>
<script id="copy-data" type="application/json">{copy_data_json}</script>
<script>
(function () {{
  var data = JSON.parse(document.getElementById("copy-data").textContent);
  var toast = document.getElementById("copy-toast");
  function showToast() {{
    toast.hidden = false;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(function () {{ toast.hidden = true; }}, 1500);
  }}
  function fallbackCopy(text) {{
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    var ok = false;
    try {{ ok = document.execCommand("copy"); }} catch (e) {{ ok = false; }}
    document.body.removeChild(ta);
    return ok;
  }}
  document.querySelectorAll(".copy-btn").forEach(function (btn) {{
    btn.addEventListener("click", function () {{
      var key = btn.getAttribute("data-copy-target");
      var text = data[key] || "";
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(text).then(showToast, function () {{
          if (fallbackCopy(text)) {{
            showToast();
          }} else {{
            alert("복사에 실패했습니다. 아래 텍스트를 직접 선택해 복사해주세요:\\n\\n" + text);
          }}
        }});
      }} else if (fallbackCopy(text)) {{
        showToast();
      }} else {{
        alert("복사에 실패했습니다. 아래 텍스트를 직접 선택해 복사해주세요:\\n\\n" + text);
      }}
    }});
  }});
}})();
</script>
<script>
(function () {{
  var REPO = "hdec-daily-news/daily-morning-news";
  var WORKFLOW = "daily-update.yml";
  var TOKEN_KEY = "gh_pat_daily_news";
  var LAST_RUN_KEY = "gh_pat_daily_news_last_run";
  var COOLDOWN_MS = 3 * 60 * 1000;

  var btn = document.getElementById("refresh-btn");
  var note = document.getElementById("refresh-note");
  if (!btn) return;

  function showNote(text) {{
    note.textContent = text;
    note.hidden = false;
  }}

  function resetBtn(label) {{
    btn.disabled = false;
    btn.textContent = label || "🔄 지금 업데이트";
  }}

  function getToken() {{
    try {{ return localStorage.getItem(TOKEN_KEY); }} catch (e) {{ return null; }}
  }}

  function promptToken() {{
    var t = window.prompt(
      "GitHub 개인 토큰(최초 1회만 입력, 이 브라우저에만 저장됨)을 붙여넣으세요.\\n\\n" +
      "만드는 법: GitHub 로그인 → 우측상단 프로필 → Settings → Developer settings → " +
      "Personal access tokens → Fine-grained tokens → Generate new token\\n" +
      "- Repository access: hdec-daily-news/daily-morning-news 만 선택\\n" +
      "- Permissions: Actions = Read and write"
    );
    if (t && t.trim()) {{
      try {{ localStorage.setItem(TOKEN_KEY, t.trim()); }} catch (e) {{}}
      return t.trim();
    }}
    return null;
  }}

  function triggerUpdate() {{
    try {{
      var last = parseInt(localStorage.getItem(LAST_RUN_KEY) || "0", 10);
      if (Date.now() - last < COOLDOWN_MS) {{
        showNote("방금 요청했어요. 잠시 후 다시 눌러주세요.");
        return;
      }}
    }} catch (e) {{}}

    var token = getToken();
    if (!token) {{
      token = promptToken();
      if (!token) return;
    }}

    btn.disabled = true;
    btn.textContent = "⏳ 요청 중...";
    note.hidden = true;

    fetch("https://api.github.com/repos/" + REPO + "/actions/workflows/" + WORKFLOW + "/dispatches", {{
      method: "POST",
      headers: {{
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json"
      }},
      body: JSON.stringify({{ ref: "main" }})
    }}).then(function (r) {{
      if (r.status === 204) {{
        try {{ localStorage.setItem(LAST_RUN_KEY, String(Date.now())); }} catch (e) {{}}
        showNote("✅ 업데이트 요청됨 — 2~3분 후 새로고침 해주세요.");
        resetBtn();
      }} else if (r.status === 401 || r.status === 403) {{
        try {{ localStorage.removeItem(TOKEN_KEY); }} catch (e) {{}}
        showNote("토큰이 유효하지 않습니다. 다시 눌러서 새 토큰을 입력해주세요.");
        resetBtn();
      }} else {{
        r.text().then(function (t) {{
          showNote("요청 실패(status " + r.status + "). 잠시 후 다시 시도해주세요.");
        }});
        resetBtn();
      }}
    }}).catch(function () {{
      showNote("네트워크 오류로 요청에 실패했습니다.");
      resetBtn();
    }});
  }}

  btn.addEventListener("click", triggerUpdate);
}})();
</script>
</body>
</html>
"""

# 사람이 직접 쓰던 양식(example/briefings/*.txt)과 동일하게 맞춘다(2026-07-22):
# "■ {섹터명} {날짜}"는 첫 섹터(정치)에만 붙고, 이후 섹터는 날짜 없이 "■ {섹터명}"만 쓴다.
# 기사는 "[언론사] 헤드라인" 다음 줄에 링크, 기사와 기사 사이에 빈 줄 하나.
def sector_copy_text(sector, date_label=None):
    header = f"■ {sector['label']}"
    if date_label:
        header += f" {date_label}"
    lines = [header, ""]
    if sector["articles"]:
        for a in sector["articles"]:
            lines.append(a["title"])
            lines.append(a["link"])
            lines.append("")
        lines.pop()
    else:
        lines.append("(해당 시간대 기사 없음)")
    return "\n".join(lines)


def render_sector(sector):
    items = sector["articles"]
    lis = "\n".join(
        f'    <li><a href="{a["link"]}" target="_blank" rel="noopener">{a["title"]}</a></li>' for a in items
    ) or '    <li class="empty">(해당 시간대 기사 없음)</li>'
    key = sector["key"]
    return f"""  <div class="sector">
    <div class="sector-head">
      <h3>■ {sector['label']}</h3>
      <button class="copy-btn" data-copy-target="sector-{key}" type="button">복사</button>
    </div>
    <ul>
{lis}
    </ul>
  </div>"""


def _image_card(img, link, label, extra_class=""):
    img_name = os.path.basename(img)
    cls = f"card {extra_class}".strip()
    return (
        f'    <div class="{cls}">\n'
        f'      <a class="card-thumb" href="{link}" target="_blank" rel="noopener">'
        f'<img src="{img}" alt="{label}" loading="lazy"></a>\n'
        f'      <span>{label}</span>\n'
        f'      <a class="dl-btn" href="{img}" download="{img_name}">⬇ 이미지 다운로드</a>\n'
        f'    </div>'
    )


def render_gallery(images):
    cards = []
    for item in images:
        img = item.get("image")
        if not img or not item.get("ok", True):
            continue
        cards.append(_image_card(img, item["link"], item["title"]))
    return "\n".join(cards) or "    <p>캡쳐된 이미지가 없습니다.</p>"


def render_infographics(images, graphics_items):
    cards = []
    for item in images:
        for info in item.get("infographics", []):
            img = info.get("image")
            if not img:
                continue
            label = info.get("caption") or item.get("title", "")
            cards.append(_image_card(img, item["link"], label, extra_class="infographic-card"))
    for g in graphics_items:
        img = g.get("image")
        if not img:
            continue
        label = f"[{g.get('source', '')}] {g.get('title', '')}".strip()
        cards.append(_image_card(img, g.get("link", "#"), label, extra_class="infographic-card"))
    return "\n".join(cards) or "    <p>오늘은 인포그래픽/차트가 발견되지 않았습니다.</p>", len(cards)


def build_images_zip(articles, graphics_items, out_path):
    """캡쳐 이미지 + 인포그래픽(기사 내 발견분 + 통신사 그래픽 코너 수집분)을 모두 모아
    ZIP 하나로 묶는다 (모바일에서 원탭 일괄 다운로드용)."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in articles:
            img = item.get("image")
            if img and item.get("ok", True) and os.path.exists(img):
                zf.write(img, arcname=os.path.basename(img))
                count += 1
            for info in item.get("infographics", []):
                info_img = info.get("image")
                if info_img and os.path.exists(info_img):
                    zf.write(info_img, arcname=f"infographics/{os.path.basename(info_img)}")
                    count += 1
        for g in graphics_items:
            g_img = g.get("image")
            if g_img and os.path.exists(g_img):
                zf.write(g_img, arcname=f"graphics/{os.path.basename(g_img)}")
                count += 1
    return count


def main():
    with open("data/links.json", encoding="utf-8") as f:
        links_data = json.load(f)

    images_data = {"articles": []}
    if os.path.exists("data/images.json"):
        with open("data/images.json", encoding="utf-8") as f:
            images_data = json.load(f)

    graphics_data = {"items": []}
    if os.path.exists("data/graphics.json"):
        with open("data/graphics.json", encoding="utf-8") as f:
            graphics_data = json.load(f)

    sectors_html = "\n".join(render_sector(s) for s in links_data["sectors"])
    gallery_html = render_gallery(images_data.get("articles", []))
    ok_images = [a for a in images_data.get("articles", []) if a.get("ok", True) and a.get("image")]
    infographics_html, infographic_count = render_infographics(
        images_data.get("articles", []), graphics_data.get("items", [])
    )
    total_image_count = build_images_zip(
        images_data.get("articles", []), graphics_data.get("items", []), "output/images.zip"
    )

    sectors = links_data["sectors"]
    date_label = links_data["date_label"]
    sector_texts_list = [
        sector_copy_text(s, date_label=date_label if i == 0 else None) for i, s in enumerate(sectors)
    ]
    sector_texts = {f"sector-{s['key']}": text for s, text in zip(sectors, sector_texts_list)}
    all_text = "\n\n".join(sector_texts_list)
    copy_data = dict(sector_texts, **{"copy-all-text": all_text})

    html = TEMPLATE.format(
        date_label=links_data["date_label"],
        window_start=links_data["window_start"][:16].replace("T", " "),
        window_end=links_data["window_end"][:16].replace("T", " "),
        sectors_html=sectors_html,
        gallery_html=gallery_html,
        image_count=len(ok_images),
        infographics_html=infographics_html,
        infographic_count=infographic_count,
        total_image_count=total_image_count,
        copy_data_json=json.dumps(copy_data, ensure_ascii=False).replace("</", "<\\/"),
    )
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("[OK] index.html 생성 완료")


if __name__ == "__main__":
    main()
