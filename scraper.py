"""
gds WM Tippspiel 2026 — Datenscraper
Holt Daten von Kicktipp + football-data.org, schreibt data.json
"""
import os, json, csv, io, time, sys, traceback, requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

KICKTIPP_BASE       = "https://www.kicktipp.de"
KICKTIPP_GROUP      = "gds-wm-tippspiel2026"
FOOTBALL_API_BASE   = "https://api.football-data.org/v4"
WM_COMPETITION_CODE = "WC"
OUTPUT_FILE         = "data.json"

FLAG_MAP = {
    "Mexico":"🇲🇽","Canada":"🇨🇦","United States":"🇺🇸","Brazil":"🇧🇷",
    "Argentina":"🇦🇷","Germany":"🇩🇪","France":"🇫🇷","Spain":"🇪🇸",
    "Portugal":"🇵🇹","England":"🏴󠁧󠁢󠁥󠁮󠁧󠁿","Netherlands":"🇳🇱","Belgium":"🇧🇪",
    "Uruguay":"🇺🇾","Colombia":"🇨🇴","Chile":"🇨🇱","Japan":"🇯🇵",
    "South Korea":"🇰🇷","Australia":"🇦🇺","Morocco":"🇲🇦","Senegal":"🇸🇳",
    "Nigeria":"🇳🇬","Saudi Arabia":"🇸🇦","Iran":"🇮🇷","Switzerland":"🇨🇭",
    "Croatia":"🇭🇷","Denmark":"🇩🇰","Poland":"🇵🇱","Serbia":"🇷🇸",
    "Scotland":"🏴󠁧󠁢󠁳󠁣󠁴󠁿","Wales":"🏴󠁧󠁢󠁷󠁬󠁳󠁿","Ecuador":"🇪🇨","Qatar":"🇶🇦",
    "Ghana":"🇬🇭","Cameroon":"🇨🇲","Tunisia":"🇹🇳","Costa Rica":"🇨🇷",
    "Panama":"🇵🇦","Honduras":"🇭🇳","Jamaica":"🇯🇲","Peru":"🇵🇪",
    "Venezuela":"🇻🇪","Indonesia":"🇮🇩","New Zealand":"🇳🇿","USA":"🇺🇸",
}

class KicktippScraper:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "de-DE,de;q=0.9",
        })

    def login(self):
        print(f"[Kicktipp] Login als {self.email[:4]}***...")
        try:
            # Login-Seite laden um CSRF-Token zu holen
            r = self.session.get(f"{KICKTIPP_BASE}/info/login", timeout=30)
            print(f"[Kicktipp] Login-Seite: HTTP {r.status_code}")
            soup = BeautifulSoup(r.text, "html.parser")

            # Alle hidden inputs holen
            form = soup.find("form")
            payload = {}
            if form:
                for inp in form.find_all("input", {"type": "hidden"}):
                    if inp.get("name"):
                        payload[inp["name"]] = inp.get("value", "")
                print(f"[Kicktipp] Formular-Felder gefunden: {list(payload.keys())}")

            payload["login_email"]    = self.email
            payload["login_password"] = self.password

            r2 = self.session.post(
                f"{KICKTIPP_BASE}/info/login",
                data=payload,
                allow_redirects=True,
                timeout=30
            )
            print(f"[Kicktipp] POST Login: HTTP {r2.status_code}, URL nach Redirect: {r2.url}")

            # Login-Erfolg prüfen
            if "logout" in r2.text.lower() or "/info/login" not in r2.url:
                print("[Kicktipp] Login erfolgreich!")
                return True

            # Fehlermeldung aus der Seite lesen
            soup2 = BeautifulSoup(r2.text, "html.parser")
            err = soup2.find(class_=lambda c: c and "error" in c.lower())
            if err:
                print(f"[Kicktipp] Login-Fehler auf Seite: {err.get_text(strip=True)}")
            else:
                print("[Kicktipp] Login fehlgeschlagen — kein Logout-Link, aber auch kein Fehlertext gefunden.")
                print(f"[Kicktipp] Seiten-Titel: {soup2.title.string if soup2.title else 'kein Titel'}")
            return False

        except Exception as e:
            print(f"[Kicktipp] Exception beim Login: {e}")
            traceback.print_exc()
            return False

    def get_rangliste_csv(self):
        """CSV-Export Gesamtübersicht Einzelwertung"""
        print("[Kicktipp] Lade Ranglisten-CSV...")
        urls_to_try = [
            f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/datenexport/rangliste?typ=gesamtuebersicht&wertung=einzelwertung",
            f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/datenexport?rangliste=1",
            f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/rangliste",
        ]
        for url in urls_to_try:
            try:
                r = self.session.get(url, timeout=30)
                print(f"[Kicktipp] CSV-URL {url}: HTTP {r.status_code}, Content-Type: {r.headers.get('content-type','?')}")
                if r.status_code == 200 and (";" in r.text[:200] or "Name" in r.text[:200]):
                    rows = list(csv.DictReader(io.StringIO(r.text), delimiter=";", quotechar='"'))
                    if rows and len(rows) > 1:
                        print(f"[Kicktipp] {len(rows)} Zeilen, Spalten: {list(rows[0].keys())}")
                        return rows
            except Exception as e:
                print(f"[Kicktipp] Fehler bei {url}: {e}")
        return self._scrape_rangliste_html()

    def _scrape_rangliste_html(self):
        """Fallback: Rangliste direkt von HTML scrapen"""
        print("[Kicktipp] Fallback: Scrape HTML-Rangliste...")
        r = self.session.get(f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/rangliste", timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        rows = []
        table = soup.find("table")
        if not table:
            print("[Kicktipp] Keine Tabelle auf Rangliste-Seite gefunden!")
            return []
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        print(f"[Kicktipp] HTML-Tabellen-Header: {headers}")
        for tr in table.find_all("tr")[1:]:
            tds = [td.get_text(strip=True) for td in tr.find_all("td")]
            if tds and len(tds) >= 2:
                row = dict(zip(headers, tds))
                rows.append(row)
        print(f"[Kicktipp] {len(rows)} Zeilen aus HTML-Fallback")
        return rows

    @staticmethod
    def parse_rangliste_csv(rows):
        if not rows:
            return {}
        header = list(rows[0].keys())
        print(f"[Parse] Alle Spalten: {header}")
        spieltag_cols = [k for k in header if "spieltag" in k.lower()]
        print(f"[Parse] Spieltag-Spalten: {spieltag_cols}")
        result = {}
        for st_idx, col in enumerate(spieltag_cols, start=1):
            st_data = []
            for row in rows:
                pts_kumuliert = 0
                for prev_col in spieltag_cols[:st_idx]:
                    v = str(row.get(prev_col, "")).strip()
                    pts_kumuliert += int(v) if v.lstrip("-").isdigit() else 0
                st_data.append({
                    "name":         str(row.get("Name", "")).strip(),
                    "pts_spieltag": int(str(row.get(col,"0")).strip()) if str(row.get(col,"0")).strip().lstrip("-").isdigit() else 0,
                    "pts_gesamt":   pts_kumuliert,
                    "rang":         str(row.get("Rang", "0")).strip(),
                })
            st_data = [r for r in st_data if r["name"]]
            st_data.sort(key=lambda x: x["pts_gesamt"], reverse=True)
            if st_idx > 1 and (st_idx - 1) in result:
                prev = {p["name"]: i+1 for i, p in enumerate(result[st_idx-1])}
                for i, p in enumerate(st_data):
                    p["delta"] = prev.get(p["name"], i+1) - (i+1)
            else:
                for p in st_data:
                    p["delta"] = 0
            result[st_idx] = st_data
        return result


class FootballAPI:
    def __init__(self, api_key):
        self.session = requests.Session()
        self.session.headers.update({"X-Auth-Token": api_key})

    def get_wm_matches(self):
        print("[Football-API] Lade WM-Spiele...")
        url = f"{FOOTBALL_API_BASE}/competitions/{WM_COMPETITION_CODE}/matches"
        r = self.session.get(url, timeout=30)
        if r.status_code == 429:
            print("[Football-API] Rate limit, 60s warten...")
            time.sleep(60)
            r = self.session.get(url, timeout=30)
        print(f"[Football-API] HTTP {r.status_code}")
        if r.status_code != 200:
            print(f"[Football-API] Fehler: {r.text[:300]}")
            return []
        matches = r.json().get("matches", [])
        print(f"[Football-API] {len(matches)} Spiele geladen")
        return matches

    @staticmethod
    def parse_matches(matches):
        by_spieltag = {}
        for m in matches:
            md = m.get("matchday")
            if not md:
                continue
            status_raw = m.get("status", "SCHEDULED")
            if status_raw == "FINISHED":
                status = "finished"
            elif status_raw in ("IN_PLAY","PAUSED","HALF_TIME"):
                status = "live"
            else:
                status = "upcoming"
            ft = m.get("score",{}).get("fullTime",{})
            hg, ag = ft.get("home"), ft.get("away")
            if status == "finished" and hg is not None:
                score = f"{hg}:{ag}"
            elif status == "live":
                score = f"{hg or 0}:{ag or 0}"
            else:
                score = "—"
            utc = m.get("utcDate","")
            try:
                import zoneinfo
                dt = datetime.fromisoformat(utc.replace("Z","+00:00"))
                dt_local = dt.astimezone(zoneinfo.ZoneInfo("Europe/Berlin"))
                zeit = "Abpfiff" if status=="finished" else ("LIVE" if status=="live" else dt_local.strftime("%H:%M"))
            except:
                zeit = utc[:10]
            heim = m.get("homeTeam",{}).get("name","")
            gast = m.get("awayTeam",{}).get("name","")
            by_spieltag.setdefault(md,[]).append({
                "heim": {"name": heim, "flag": FLAG_MAP.get(heim,"🏳️")},
                "gast": {"name": gast, "flag": FLAG_MAP.get(gast,"🏳️")},
                "score": score, "status": status, "zeit": zeit, "tipps": [],
            })
        return by_spieltag


def main():
    email    = os.environ.get("KICKTIPP_EMAIL","")
    password = os.environ.get("KICKTIPP_PASSWORD","")
    api_key  = os.environ.get("FOOTBALL_API_KEY","")

    print(f"[Start] Email gesetzt: {'ja' if email else 'NEIN'}")
    print(f"[Start] Password gesetzt: {'ja' if password else 'NEIN'}")
    print(f"[Start] API-Key gesetzt: {'ja' if api_key else 'nein (optional)'}")

    if not email or not password:
        print("FEHLER: KICKTIPP_EMAIL und KICKTIPP_PASSWORD müssen als GitHub Secrets gesetzt sein!")
        sys.exit(1)

    # Kicktipp
    kt = KicktippScraper(email, password)
    login_ok = kt.login()
    if not login_ok:
        print("FEHLER: Kicktipp-Login fehlgeschlagen!")
        print("Prüfe: 1) Secrets korrekt geschrieben? 2) Passwort stimmt? 3) Kicktipp-Account aktiv?")
        sys.exit(1)

    csv_rows  = kt.get_rangliste_csv()
    rangliste = KicktippScraper.parse_rangliste_csv(csv_rows)

    # Football API
    spiele_by_spieltag = {}
    if api_key:
        fapi = FootballAPI(api_key)
        matches = fapi.get_wm_matches()
        spiele_by_spieltag = FootballAPI.parse_matches(matches)

    # Aktiven Spieltag bestimmen
    aktiver_spieltag = max(rangliste.keys()) if rangliste else 1
    for st_id, spiele in spiele_by_spieltag.items():
        if any(s["status"] in ("finished","live") for s in spiele):
            aktiver_spieltag = max(aktiver_spieltag, st_id)

    alle_st = sorted(set(list(rangliste.keys()) + list(spiele_by_spieltag.keys())))
    spieltag_meta = [{"id":i,"label":f"Spieltag {i}","aktiv":i==aktiver_spieltag,"zukuenftig":i>aktiver_spieltag} for i in alle_st]

    output = {
        "meta": {"generiert_am": datetime.now(timezone.utc).isoformat(), "aktiver_spieltag": aktiver_spieltag, "quelle": KICKTIPP_GROUP},
        "spieltage":  spieltag_meta,
        "ranglisten": {str(k): v for k,v in rangliste.items()},
        "spiele":     {str(k): v for k,v in spiele_by_spieltag.items()},
    }
    with open(OUTPUT_FILE,"w",encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✓ {OUTPUT_FILE} geschrieben — {len(rangliste)} Spieltage, {sum(len(v) for v in spiele_by_spieltag.values())} Spiele")

if __name__ == "__main__":
    main()
