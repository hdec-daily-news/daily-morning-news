# Daily Morning News

현대건설 글로벌사업부 경영층용 일일 정치/정당/경제 뉴스 자동 큐레이션.
매일 아침 GitHub Actions가 자동 실행되어 GitHub Pages에 결과를 게시한다.

- 프로젝트1: 정치 주요기사 / 더불어민주당 동정 / 국민의힘 동정 / 경제 동정 — 링크+헤드라인 (엑셀 다운로드도 제공)
- 프로젝트2: 네이버 메인 뉴스 전반의 기사 "메인화면" 캡쳐 이미지 갤러리

상세 기준(섹터 구성, 시간필터, 캡쳐 범위 등)은 `일일 정치 주요뉴스` 폴더의 `CLAUDE.md`를 참고.

## 최초 설정 (1회만)

### 1. GitHub 저장소 생성
GitHub에서 새 저장소 생성 (이름: `daily-morning-news`, Public — GitHub Pages 무료로 쓰려면 Public 권장).
**절대 이 폴더를 그대로 올리기 전에 API 키가 코드에 하드코딩되어 있지 않은지 확인할 것** (현재는 안전하게 환경변수 방식으로 되어 있음).

### 2. 이 폴더를 저장소에 push

```powershell
cd "daily-morning-news"
git init
git add -A
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<본인계정>/daily-morning-news.git
git push -u origin main
```

### 3. API 키 등록 (GitHub Secrets)
저장소 → Settings → Secrets and variables → Actions → New repository secret

- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`

(네이버 개발자 센터에서 발급받은 값. HDEC Daily News Hub와 같은 계정 키를 재사용해도 되지만, 이 저장소의 Secrets에 별도로 등록해서 코드/설정은 분리 관리한다.)

### 4. GitHub Pages 활성화
저장소 → Settings → Pages → Source: `Deploy from a branch` → Branch: `main` / `/(root)` 선택 → Save.
몇 분 후 `https://<본인계정>.github.io/daily-morning-news/` 에서 확인 가능.

### 5. 수동 실행으로 테스트
저장소 → Actions → "Daily Morning News Update" → Run workflow 로 즉시 1회 실행해서 결과 확인.

## ⚠️ 알려진 한계 (첫 실행 후 보정 필요)

`capture_images.py`의 네이버 뉴스 페이지 선택자(CSS selector)는 실제 네이버 페이지에 접속해서
테스트하지 못한 상태로 작성되었다 (작성 환경 자체가 네트워크 차단 샌드박스였음).
첫 Actions 실행 후 `images/` 폴더의 캡쳐 이미지를 확인하고, 캡쳐 범위가 어긋나면
`HEADER_SELECTORS`, `BODY_SELECTORS`, `LIST_LINK_SELECTORS`, clip 계산 로직을 조정해야 한다.

## 로컬 테스트

```powershell
pip install -r requirements.txt
playwright install chromium
$env:NAVER_CLIENT_ID="..."
$env:NAVER_CLIENT_SECRET="..."
python collect_links.py
python build_excel.py
python capture_images.py
python build_page.py
```

## 스케줄

`.github/workflows/daily-update.yml` — 매일 21:03 UTC(=06:03 KST) 자동 실행, 06:30 KST까지 게시 완료 목표.
뉴스 시간필터는 전일 22:00~당일 06:00(KST). 시간 조정하고 싶으면 해당 파일의 `cron` 값과
`collect_links.py`의 `get_window()`를 함께 수정.
