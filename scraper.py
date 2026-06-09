"""
gds WM Tippspiel 2026 - Datenscraper
Holt: Kicktipp (Login + Rangliste + Tipps) + football-data.org (Ergebnisse)
Schreibt: data.json
"""
import os, json, csv, io, time, sys, traceback, requests, zoneinfo
from datetime import datetime, timezone
from bs4 import BeautifulSoup

KICKTIPP_BASE       = "https://www.kicktipp.de"
KICKTIPP_GROUP      = "gds-wm-tippspiel2026"
FOOTBALL_API_BASE   = "https://api.football-data.org/v4"
WM_COMPETITION_CODE = "WC"
OUTPUT_FILE         = "data.json"
BERLIN              = zoneinfo.ZoneInfo("Europe/Berlin")

FLAG_MAP = {
    "Mexico":"🇲🇽","Canada":"🇨🇦","United States":"🇺🇸","USA":"🇺🇸",
    "Panama":"🇵🇦","Honduras":"🇭🇳","Jamaica":"🇯🇲","Costa Rica":"🇨🇷",
    "Haiti":"🇭🇹","Curacao":"🇨🇼","Brazil":"🇧🇷","Argentina":"🇦🇷",
    "Colombia":"🇨🇴","Uruguay":"🇺🇾","Chile":"🇨🇱","Ecuador":"🇪🇨",
    "Peru":"🇵🇪","Venezuela":"🇻🇪","Paraguay":"🇵🇾","Bolivia":"🇧🇴",
    "Germany":"🇩🇪","France":"🇫🇷","Spain":"🇪🇸","Portugal":"🇵🇹",
    "England":"🇬🇧","Netherlands":"🇳🇱","Belgium":"🇧🇪","Switzerland":"🇨🇭",
    "Croatia":"🇭🇷","Denmark":"🇩🇰","Poland":"🇵🇱","Serbia":"🇷🇸",
    "Scotland":"🏴","Wales":"🏴","Austria":"🇦🇹","Sweden":"🇸🇪",
    "Norway":"🇳🇴","Turkey":"🇹🇷","Czechia":"🇨🇿","Czech Republic":"🇨🇿",
    "Slovakia":"🇸🇰","Hungary":"🇭🇺","Romania":"🇷🇴","Ukraine":"🇺🇦",
    "Greece":"🇬🇷","Bosnia-Herzegovina":"🇧🇦","Bosnia Herzegovina":"🇧🇦",
    "Slovenia":"🇸🇮","Iceland":"🇮🇸","Finland":"🇫🇮","Ireland":"🇮🇪",
    "Morocco":"🇲🇦","Senegal":"🇸🇳","Nigeria":"🇳🇬","Ghana":"🇬🇭",
    "Cameroon":"🇨🇲","Tunisia":"🇹🇳","Egypt":"🇪🇬","Algeria":"🇩🇿",
    "South Africa":"🇿🇦","Ivory Coast":"🇨🇮","Congo DR":"🇨🇩","DR Congo":"🇨🇩",
    "Cape Verde Islands":"🇨🇻","Cape Verde":"🇨🇻","Japan":"🇯🇵",
    "South Korea":"🇰🇷","Saudi Arabia":"🇸🇦","Iran":"🇮🇷","Australia":"🇦🇺",
    "Qatar":"🇶🇦","Uzbekistan":"🇺🇿","Indonesia":"🇮🇩","Jordan":"🇯🇴",
    "Iraq":"🇮🇶","New Zealand":"🇳🇿",
}

# Kicktipp DE-Namen → football-data EN-Namen
NAME_MAP = {
    "Deutschland":"Germany","Frankreich":"France","Spanien":"Spain",
    "Niederlande":"Netherlands","Belgien":"Belgium","Schweiz":"Switzerland",
    "Kroatien":"Croatia","Daenemark":"Denmark","Dänemark":"Denmark",
    "Polen":"Poland","Serbien":"Serbia","Schottland":"Scotland",
    "Oesterreich":"Austria","Österreich":"Austria","Schweden":"Sweden",
    "Norwegen":"Norway","Tuerkei":"Turkey","Türkei":"Turkey",
    "Tschechien":"Czechia","Brasilien":"Brazil","Argentinien":"Argentina",
    "Kolumbien":"Colombia","Mexiko":"Mexico","USA":"United States",
    "Kanada":"Canada","Marokko":"Morocco","Aegypten":"Egypt","Ägypten":"Egypt",
    "Algerien":"Algeria","Suedafrika":"South Africa","Südafrika":"South Africa",
    "Elfenbeinkueste":"Ivory Coast","Elfenbeinküste":"Ivory Coast",
    "Kongo DR":"Congo DR","Kap Verde":"Cape Verde Islands",
    "Suedkorea":"South Korea","Südkorea":"South Korea",
    "Saudi-Arabien":"Saudi Arabia","Australien":"Australia",
    "Katar":"Qatar","Usbekistan":"Uzbekistan","Jordanien":"Jordan",
    "Irak":"Iraq","Neuseeland":"New Zealand","Tunesien":"Tunisia",
    "Kamerun":"Cameroon","Uruguay":"Uruguay","Paraguay":"Paraguay",
    "Ecuador":"Ecuador","Iran":"Iran","Senegal":"Senegal","Ghana":"Ghana",
    "Nigeria":"Nigeria","Haiti":"Haiti","Bosnien-Herzegowina":"Bosnia-Herzegovina",
}


class KicktippScraper:
    def __init__(self, email, password):
        self.email    = email
        self.password = password
        self.session  = requests.Session()
        self.session.headers.update({
            "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "de-DE,de;q=0.9",
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    # ── LOGIN ────────────────────────────────────────────────────
    def login(self) -> bool:
        print(f"[Kicktipp] Login als {self.email[:4]}***...")
        try:
            # Startseite der Gruppe laden um Session-Cookie zu bekommen
            r0 = self.session.get(f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}", timeout=30)
            print(f"[Kicktipp] Startseite: HTTP {r0.status_code}")

            # Login-Seite laden
            login_url = f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/profil/login"
            r = self.session.get(login_url, timeout=30)
            print(f"[Kicktipp] Login-Seite: HTTP {r.status_code}")
            soup = BeautifulSoup(r.text, "html.parser")

            # Formular finden und Action-URL + alle hidden fields holen
            form = soup.find("form")
            action_url = login_url  # Fallback
            payload = {}
            if form:
                if form.get("action"):
                    action = form["action"]
                    action_url = action if action.startswith("http") else KICKTIPP_BASE + action
                for inp in form.find_all("input"):
                    name = inp.get("name","")
                    val  = inp.get("value","")
                    if name:
                        payload[name] = val
                print(f"[Kicktipp] Form action: {action_url}")
                print(f"[Kicktipp] Hidden fields: {[k for k,v in payload.items() if k not in ('login_email','login_password')]}")

            payload["login_email"]    = self.email
            payload["login_password"] = self.password
            # Kicktipp verwendet "kennung" und "passwort" als Feldnamen
            payload["kennung"]  = self.email
            payload["passwort"] = self.password

            r2 = self.session.post(action_url, data=payload, allow_redirects=True, timeout=30)
            print(f"[Kicktipp] POST Login: HTTP {r2.status_code}, finale URL: {r2.url}")

            # Erfolg: URL ist nicht mehr die Login-Seite ODER enthält logout-Link
            soup2 = BeautifulSoup(r2.text, "html.parser")
            hat_logout = bool(soup2.find("a", href=lambda h: h and "logout" in h.lower()))
            noch_login  = "profil/login" in r2.url and not hat_logout

            if hat_logout or not noch_login:
                print("[Kicktipp] Login erfolgreich!")
                return True

            for sel in [".error",".alert",".message","#error",".formError"]:
                el = soup2.select_one(sel)
                if el:
                    print(f"[Kicktipp] Fehlermeldung: {el.get_text(strip=True)}")
                    break
            else:
                print("[Kicktipp] Login fehlgeschlagen — Seiten-Titel:", soup2.title.string if soup2.title else "?")
            return False

        except Exception as e:
            print(f"[Kicktipp] Exception beim Login: {e}")
            traceback.print_exc()
            return False

    # ── RANGLISTE ────────────────────────────────────────────────
    def get_rangliste_csv(self) -> list:
        """Lädt den Gesamtübersicht-Einzelwertung CSV-Export via POST (wie das UI)."""
        print("[Kicktipp] Lade Ranglisten-CSV...")

        # Schritt 1: Datenexport-Seite laden um CSRF-Token zu holen
        export_page_url = f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/datenexport"
        try:
            r = self.session.get(export_page_url, timeout=30)
            print(f"[Kicktipp] Datenexport-Seite: HTTP {r.status_code}")
            soup = BeautifulSoup(r.text, "html.parser")

            # Formular finden
            form = soup.find("form")
            payload = {}
            action_url = export_page_url
            if form:
                if form.get("action"):
                    action = form["action"]
                    action_url = action if action.startswith("http") else KICKTIPP_BASE + action
                for inp in form.find_all("input"):
                    if inp.get("name"):
                        payload[inp["name"]] = inp.get("value", "")
                print(f"[Kicktipp] Export-Form action: {action_url}")
                print(f"[Kicktipp] Export-Form fields: {list(payload.keys())}")

            # Schritt 2: POST mit den richtigen Dropdown-Werten
            # Aus dem Screenshot: Auswahl=Rangliste, Spieltag=1.Spieltag, Wertung=Einzelwertung
            payload["typ"]     = "gesamtuebersicht"   # Dropdown "Auswahl der Daten"
            payload["wertung"] = "einzelwertung"       # Dropdown "Wertung"

            # Auch Select-Felder aus dem Formular übernehmen
            for sel in soup.find_all("select"):
                name = sel.get("name", "")
                if name and name not in payload:
                    # Ersten Option-Wert nehmen
                    opt = sel.find("option")
                    payload[name] = opt["value"] if opt and opt.get("value") else ""

            print(f"[Kicktipp] POST payload: {payload}")
            r2 = self.session.post(action_url, data=payload, timeout=30)
            print(f"[Kicktipp] Export POST: HTTP {r2.status_code}, CT: {r2.headers.get('content-type','?')[:50]}")

            if r2.status_code == 200 and ";" in r2.text[:500]:
                rows = list(csv.DictReader(io.StringIO(r2.text), delimiter=";", quotechar='"'))
                if rows:
                    print(f"[Kicktipp] CSV OK: {len(rows)} Zeilen, Spalten: {list(rows[0].keys())}")
                    # Validierung: muss eine "Name"-Spalte haben mit echten Teilnehmernamen
                    # Kicktipp-Rangliste hat immer "Rang" und "Name"
                    has_name = any("name" in k.lower() for k in rows[0].keys())
                    # Sanity-check: Werte in Name-Spalte dürfen keine Wertungstypen sein
                    name_col = next((k for k in rows[0].keys() if "name" in k.lower()), None)
                    fake_namen = {"heim","gast","gruppe","ergebnis","tendenz"}
                    if name_col:
                        echte_namen = [r[name_col].strip().lower() for r in rows
                                       if r.get(name_col,"").strip().lower() not in fake_namen]
                    else:
                        echte_namen = []

                    if has_name and echte_namen:
                        return rows
                    else:
                        print(f"[Kicktipp] CSV enthält keine echten Teilnehmernamen — ignoriert")
                        print(f"[Kicktipp] Spalten waren: {list(rows[0].keys())}")
                        print(f"[Kicktipp] Erste Werte: {[r.get(name_col,'?') for r in rows[:5]]}")
                print("[Kicktipp] CSV leer oder ungültig")
                print(f"[Kicktipp] Antwort-Vorschau: {r2.text[:300]}")
            else:
                print(f"[Kicktipp] Unerwartete Antwort: {r2.text[:200]}")

        except Exception as e:
            print(f"[Kicktipp] Datenexport Fehler: {e}")
            traceback.print_exc()

        print("[Kicktipp] CSV-Export fehlgeschlagen — HTML-Fallback")
        return self._scrape_rangliste_html()

    def _scrape_rangliste_html(self) -> list:
        """Fallback: Rangliste aus HTML-Tabelle scrapen."""
        r = self.session.get(f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/rangliste", timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table")
        if not table:
            print("[Kicktipp] Keine Tabelle auf Rangliste-Seite")
            return []
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows = []
        for tr in table.find_all("tr")[1:]:
            tds = [td.get_text(strip=True) for td in tr.find_all("td")]
            if tds and len(tds) >= 2:
                rows.append(dict(zip(headers, tds)))
        print(f"[Kicktipp] HTML-Rangliste: {len(rows)} Zeilen")
        return rows

    def get_teilnehmer_fallback(self) -> dict:
        """Wenn WM noch nicht gestartet: Teilnehmernamen von verschiedenen Seiten."""
        print("[Kicktipp] Lade Teilnehmernamen (Pre-Tournament)...")
        namen = []

        # Versuch 1: Tippübersicht Spieltag 1 (zeigt alle Teilnehmer in Kopfzeile)
        try:
            r = self.session.get(
                f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/tippuebersicht?spieltagIndex=0",
                timeout=30)
            soup = BeautifulSoup(r.text, "html.parser")
            print(f"[Kicktipp] Tippübersicht: HTTP {r.status_code}")
            # Teilnehmer stehen in der Tabellen-Kopfzeile
            table = soup.find("table")
            if table:
                header = table.find("tr")
                if header:
                    for th in header.find_all(["th","td"])[1:]:
                        name = th.get_text(strip=True)
                        if name and len(name) > 1 and name not in namen:
                            namen.append(name)
                    print(f"[Kicktipp] Tippübersicht-Header: {namen}")
        except Exception as e:
            print(f"[Kicktipp] Tippübersicht-Fallback Fehler: {e}")

        # Versuch 2: Ranglisten-Seite — Teilnehmer aus Tabellenzellen
        if not namen:
            try:
                r = self.session.get(
                    f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/rangliste",
                    timeout=30)
                soup = BeautifulSoup(r.text, "html.parser")
                # Alle Tabellenzellen mit Tipper-Namen
                for td in soup.find_all("td", class_=lambda c: c and any(
                        x in c for x in ["name","tipper","user","teilnehmer"])):
                    name = td.get_text(strip=True)
                    if name and len(name) > 1 and name not in namen:
                        namen.append(name)
                # Fallback: alle Links die auf Profil-Seiten zeigen aber NICHT auf Sprachseiten
                if not namen:
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        name = a.get_text(strip=True)
                        if ("/profil/" in href and "login" not in href
                                and len(name) > 2 and name not in namen
                                and not name.isdigit()
                                and href != f"/{KICKTIPP_GROUP}/profil/de"):
                            namen.append(name)
                print(f"[Kicktipp] Rangliste-Fallback: {namen}")
            except Exception as e:
                print(f"[Kicktipp] Rangliste-Fallback Fehler: {e}")

        # Versuch 3: Mitgliederliste (nur für Spielleiter sichtbar, kein Schaden wenn 404)
        if not namen:
            try:
                r = self.session.get(
                    f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/mitglieder",
                    timeout=30)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    for td in soup.find_all("td"):
                        name = td.get_text(strip=True)
                        if name and len(name) > 2 and name not in namen and not name.isdigit():
                            namen.append(name)
                    print(f"[Kicktipp] Mitgliederliste: {namen}")
            except Exception as e:
                print(f"[Kicktipp] Mitgliederliste Fehler: {e}")

        print(f"[Kicktipp] {len(namen)} Teilnehmer gefunden: {namen}")
        if not namen:
            print("[Kicktipp] WARNUNG: Keine Teilnehmer gefunden — data.json bleibt ohne Rangliste")
            return {}

        return {1: [{"name": n, "pts_spieltag": 0, "pts_gesamt": 0,
                     "rang": str(i+1), "delta": 0}
                    for i, n in enumerate(namen)]}

    @staticmethod
    def parse_rangliste_csv(rows: list) -> dict:
        """CSV-Zeilen → strukturierte Rangliste pro Spieltag."""
        if not rows:
            return {}
        header = list(rows[0].keys())
        print(f"[Parse] Spalten: {header}")
        spieltag_cols = [k for k in header if "spieltag" in k.lower()]
        print(f"[Parse] Spieltag-Spalten: {spieltag_cols}")
        if not spieltag_cols:
            # Fallback: Gesamtpunkte-Spalte → Spieltag 1
            gesamt_col = next((k for k in header if "gesamt" in k.lower()), None)
            if gesamt_col:
                rows_sorted = sorted(rows, key=lambda r: int(r.get(gesamt_col,"0") or "0"), reverse=True)
                return {1: [{"name":r.get("Name","").strip(),
                              "pts_spieltag":int(r.get(gesamt_col,"0") or "0"),
                              "pts_gesamt":int(r.get(gesamt_col,"0") or "0"),
                              "rang":r.get("Rang","0").strip(), "delta":0}
                             for r in rows_sorted if r.get("Name","").strip()]}
            return {}

        result = {}
        for st_idx, col in enumerate(spieltag_cols, start=1):
            st_data = []
            for row in rows:
                kumuliert = sum(
                    int(str(row.get(c,"0")).strip()) if str(row.get(c,"0")).strip().lstrip("-").isdigit() else 0
                    for c in spieltag_cols[:st_idx]
                )
                pts_st = int(str(row.get(col,"0")).strip()) if str(row.get(col,"0")).strip().lstrip("-").isdigit() else 0
                name = str(row.get("Name","")).strip()
                if name:
                    st_data.append({"name":name,"pts_spieltag":pts_st,"pts_gesamt":kumuliert,
                                    "rang":str(row.get("Rang","0")).strip(),"delta":0})
            st_data.sort(key=lambda x: x["pts_gesamt"], reverse=True)
            if st_idx > 1 and (st_idx-1) in result:
                prev = {p["name"]:i+1 for i,p in enumerate(result[st_idx-1])}
                for i,p in enumerate(st_data):
                    p["delta"] = prev.get(p["name"], i+1) - (i+1)
            result[st_idx] = st_data
        return result

    # ── TIPPS ────────────────────────────────────────────────────
    def get_spieltag_tipps(self, spieltag: int) -> dict:
        """
        Scrapt Tippübersicht — nur nach Spielbeginn sichtbar.
        Gibt zurück: {"HeimName:GastName": [{name, tipp, result}, ...]}
        """
        print(f"[Kicktipp] Lade Tippübersicht Spieltag {spieltag}...")
        url = f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/tippuebersicht?spieltagIndex={spieltag-1}"
        try:
            r = self.session.get(url, timeout=30)
            print(f"[Kicktipp] Tippübersicht: HTTP {r.status_code}")
            if r.status_code != 200:
                return {}
        except Exception as e:
            print(f"[Kicktipp] Tippübersicht Fehler: {e}")
            return {}

        soup = BeautifulSoup(r.text, "html.parser")

        # Tabelle finden
        table = (soup.find("table", id="tippuebersicht") or
                 soup.find("table", class_=lambda c: c and "tipp" in c.lower()) or
                 soup.find("table"))
        if not table:
            print("[Kicktipp] Keine Tippübersicht-Tabelle gefunden")
            return {}

        # Teilnehmernamen aus Header-Zeile
        header_row = table.find("tr")
        teilnehmer = [th.get_text(strip=True)
                      for th in header_row.find_all(["th","td"])[1:]
                      if th.get_text(strip=True)]
        print(f"[Kicktipp] {len(teilnehmer)} Teilnehmer in Tippübersicht")

        tipps_by_spiel = {}
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td","th"])
            if len(cells) < 2:
                continue
            spiel_text = cells[0].get_text(strip=True)
            # Spiel-Key aus "Heim - Gast" bauen
            spiel_key = None
            for sep in [" - ", " – ", " vs ", " vs. "]:
                if sep in spiel_text:
                    h, g = spiel_text.split(sep, 1)
                    spiel_key = f"{h.strip()}:{g.strip()}"
                    break
            if not spiel_key:
                continue

            tipps = []
            for i, cell in enumerate(cells[1:]):
                if i >= len(teilnehmer):
                    break
                tipp_text = cell.get_text(strip=True)
                if not tipp_text or ":" not in tipp_text:
                    continue
                css = " ".join(cell.get("class", []))
                if any(x in css for x in ["richtig","correct","gewonnen"]):
                    result = True
                elif any(x in css for x in ["falsch","wrong","verloren"]):
                    result = False
                else:
                    result = None  # Spiel läuft noch
                tipps.append({"name": teilnehmer[i], "tipp": tipp_text, "result": result})

            if tipps:
                tipps_by_spiel[spiel_key] = tipps
                print(f"[Kicktipp]   {spiel_key}: {len(tipps)} Tipps")

        print(f"[Kicktipp] Spieltag {spieltag}: {len(tipps_by_spiel)} Spiele mit Tipps")
        return tipps_by_spiel

    @staticmethod
    def match_tipps_to_spiele(spiele: list, tipps_by_spiel: dict) -> list:
        """Ordnet Kicktipp-Tipps (DE-Namen) den football-data Spielen (EN-Namen) zu."""
        def norm(name):
            en = NAME_MAP.get(name, name)
            return en.lower().strip()

        result = []
        for spiel in spiele:
            heim_en = norm(spiel["heim"]["name"])
            gast_en = norm(spiel["gast"]["name"])
            matched = []

            for key, tipps in tipps_by_spiel.items():
                if ":" not in key:
                    continue
                kh, kg = key.split(":", 1)
                kh_n, kg_n = norm(kh), norm(kg)
                # Substring-Match in beide Richtungen
                if ((kh_n in heim_en or heim_en in kh_n) and
                    (kg_n in gast_en or gast_en in kg_n)):
                    matched = [{"n": t["name"], "t": t["tipp"],
                                "c": t["result"]} for t in tipps]
                    break

            sp = dict(spiel)
            sp["tipps"] = matched
            result.append(sp)
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
            print("[Football-API] Rate limit — 60s warten...")
            time.sleep(60)
            r = self.session.get(url, timeout=30)
        print(f"[Football-API] HTTP {r.status_code}")
        if r.status_code != 200:
            print(f"[Football-API] Fehler: {r.text[:200]}")
            return []
        matches = r.json().get("matches", [])
        print(f"[Football-API] {len(matches)} Spiele")
        return matches

    @staticmethod
    def parse_matches(matches):
        by_st = {}
        for m in matches:
            md = m.get("matchday")
            if not md:
                continue
            status_raw = m.get("status","SCHEDULED")
            if status_raw == "FINISHED":            status = "finished"
            elif status_raw in ("IN_PLAY","PAUSED","HALF_TIME"): status = "live"
            else:                                   status = "upcoming"

            ft = m.get("score",{}).get("fullTime",{})
            hg, ag = ft.get("home"), ft.get("away")
            if status == "finished" and hg is not None: score = f"{hg}:{ag}"
            elif status == "live":                       score = f"{hg or 0}:{ag or 0}"
            else:                                        score = "—"

            utc = m.get("utcDate","")
            try:
                dt = datetime.fromisoformat(utc.replace("Z","+00:00"))
                dt_loc = dt.astimezone(BERLIN)
                zeit = "Abpfiff" if status=="finished" else "LIVE" if status=="live" else dt_loc.strftime("%H:%M")
            except:
                zeit = utc[:10]

            heim = m.get("homeTeam",{}).get("name","")
            gast = m.get("awayTeam",{}).get("name","")
            by_st.setdefault(md,[]).append({
                "heim":  {"name":heim, "flag":FLAG_MAP.get(heim,"🏳️")},
                "gast":  {"name":gast, "flag":FLAG_MAP.get(gast,"🏳️")},
                "score": score, "status": status, "zeit": zeit, "tipps": [],
            })
        return by_st


def main():
    email   = os.environ.get("KICKTIPP_EMAIL","")
    password= os.environ.get("KICKTIPP_PASSWORD","")
    api_key = os.environ.get("FOOTBALL_API_KEY","")

    print(f"[Start] Email: {'ja' if email else 'NEIN'} | Password: {'ja' if password else 'NEIN'} | API-Key: {'ja' if api_key else 'nein'}")
    if not email or not password:
        print("FEHLER: KICKTIPP_EMAIL und KICKTIPP_PASSWORD fehlen!")
        sys.exit(1)

    # 1. Kicktipp Login
    kt = KicktippScraper(email, password)
    if not kt.login():
        print("FEHLER: Kicktipp-Login fehlgeschlagen!")
        sys.exit(1)

    # 2. Rangliste
    csv_rows  = kt.get_rangliste_csv()
    rangliste = KicktippScraper.parse_rangliste_csv(csv_rows)
    if not rangliste:
        print("[Info] Rangliste leer — Teilnehmer-Fallback...")
        rangliste = kt.get_teilnehmer_fallback()

    # Wenn immer noch leer: bestehende data.json als Basis nehmen
    if not rangliste and os.path.exists(OUTPUT_FILE):
        print("[Info] Kein Ergebnis von Kicktipp — behalte Rangliste aus vorheriger data.json")
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                existing = json.load(f)
            rangliste = {int(k): v for k, v in existing.get("ranglisten", {}).items()}
            print(f"[Info] Rangliste aus data.json geladen: {list(rangliste.keys())}")
        except Exception as e:
            print(f"[Info] data.json lesen fehlgeschlagen: {e}")

    # 3. Spielergebnisse von football-data.org
    spiele_by_spieltag = {}
    if api_key:
        fapi    = FootballAPI(api_key)
        matches = fapi.get_wm_matches()
        spiele_by_spieltag = FootballAPI.parse_matches(matches)

    # 4. Tipps scrapen — nur für Spieltage mit gestarteten Spielen
    for st_id, spiele in spiele_by_spieltag.items():
        if any(s["status"] in ("finished","live") for s in spiele):
            print(f"[Info] Spieltag {st_id} gestartet → Tipps scrapen")
            tipps = kt.get_spieltag_tipps(st_id)
            if tipps:
                spiele_by_spieltag[st_id] = KicktippScraper.match_tipps_to_spiele(spiele, tipps)
        else:
            print(f"[Info] Spieltag {st_id}: noch keine Spiele gestartet")

    # 5. Aktiven Spieltag bestimmen
    aktiver_st = max(rangliste.keys()) if rangliste else 1
    for st_id, spiele in spiele_by_spieltag.items():
        if any(s["status"] in ("finished","live") for s in spiele):
            aktiver_st = max(aktiver_st, st_id)

    alle_st = sorted(set(list(rangliste.keys()) + list(spiele_by_spieltag.keys())))
    spieltag_meta = [{"id":i,"label":f"Spieltag {i}",
                      "aktiv":i==aktiver_st,"zukuenftig":i>aktiver_st}
                     for i in alle_st]

    # 6. data.json schreiben
    output = {
        "meta": {
            "generiert_am": datetime.now(BERLIN).strftime("%d.%m.%Y %H:%M Uhr (CEST)"),
            "aktiver_spieltag": aktiver_st,
            "quelle": KICKTIPP_GROUP,
        },
        "spieltage":  spieltag_meta,
        "ranglisten": {str(k): v for k,v in rangliste.items()},
        "spiele":     {str(k): v for k,v in spiele_by_spieltag.items()},
    }
    with open(OUTPUT_FILE,"w",encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    n_spiele = sum(len(v) for v in spiele_by_spieltag.values())
    print(f"✓ {OUTPUT_FILE} — {len(rangliste)} Spieltag-Ranglisten, {n_spiele} Spiele")

if __name__ == "__main__":
    main()
