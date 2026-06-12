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

# Feste Teilnehmerliste — aus dem Kicktipp-Export vom 09.06.2026
# Wird als Starttabelle (0 Punkte) verwendet bis echte Punkte vorliegen.
# Nach Turnierstart wird diese Liste durch den CSV-Export überschrieben.
TEILNEHMER_FEST = [
    "Anne", "Annik", "Bastelwastel", "Captain", "Conny", "DennisCostaRica",
    "Hanne_Sobek", "Helmut", "JanG", "Ludger_H", "Michelle", "Olli_R",
    "Paule", "Pottkind", "thommes", "TurboTobiBVB", "UliPausS",
]

STARTTABELLE = [
    {"name": n, "pts_spieltag": 0, "pts_gesamt": 0, "rang": str(i+1), "delta": 0}
    for i, n in enumerate(TEILNEHMER_FEST)
]

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
    def get_rangliste_csv(self) -> dict:
        """
        Lädt CSV-Exporte vom Spielleiter-Datenexport via POST.
        Gibt dict zurück: {"rangliste": [...rows], "tipper": [...rows]}
        Dropdown-Werte laut Kicktipp-UI:
          - "tipper"     = Liste aller Tipper
          - "rangliste"  = Rangliste
          - "gesamtuebersicht" = Gesamtübersicht
          - "tipps"      = Tipps aller Tipper
        """
        print("[Kicktipp] Lade CSV-Exporte vom Spielleiter-Datenexport...")
        export_page_url = f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/spielleiter/datenexport"
        results = {}
        try:
            r = self.session.get(export_page_url, timeout=30)
            print(f"[Kicktipp] Datenexport-Seite: HTTP {r.status_code}")
            if r.status_code != 200:
                return results
            soup = BeautifulSoup(r.text, "html.parser")

            # Formular + Action-URL + hidden fields
            form = soup.find("form")
            base_payload = {}
            action_url = export_page_url
            if form:
                if form.get("action"):
                    action = form["action"]
                    if action.startswith("http"):
                        action_url = action
                    elif action.startswith("/"):
                        action_url = KICKTIPP_BASE + action
                    else:
                        # Relativ zur Spielleiter-Seite — Basis-URL ergänzen
                        action_url = f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/spielleiter/{action}"
                for inp in form.find_all("input"):
                    if inp.get("name"):
                        base_payload[inp["name"]] = inp.get("value", "")
                print(f"[Kicktipp] Export action: {action_url}, fields: {list(base_payload.keys())}")

            # Dropdown-Optionen loggen + Feldnamen ermitteln
            auswahl_field = "datenauswahl"  # Kicktipp-Feldname laut HTML
            for sel in soup.find_all("select"):
                name = sel.get("name", "")
                opts = [(o.get("value",""), o.get_text(strip=True)) for o in sel.find_all("option")]
                print(f"[Kicktipp] Dropdown '{name}': {opts}")
                if "auswahl" in name.lower() or "daten" in name.lower():
                    auswahl_field = name

            def do_export(typ_value, label, extra_params=None):
                payload = dict(base_payload)
                payload[auswahl_field] = typ_value
                if extra_params:
                    payload.update(extra_params)
                print(f"[Kicktipp] POST {auswahl_field}={typ_value} ({label}) → {action_url}")
                try:
                    r2 = self.session.post(action_url, data=payload, timeout=15)
                    print(f"[Kicktipp] {label}: HTTP {r2.status_code}, CT: {r2.headers.get('content-type','?')[:50]}")
                    if r2.status_code != 200:
                        return []

                    raw = r2.content

                    # ZIP-Datei erkennen (Magic Bytes PK\x03\x04)
                    if raw[:2] == b'PK':
                        print(f"[Kicktipp] {label}: ZIP erkannt → entpacke CSV")
                        import zipfile
                        zf = zipfile.ZipFile(io.BytesIO(raw))
                        csv_files = [n for n in zf.namelist() if n.endswith('.csv')]
                        if not csv_files:
                            print(f"[Kicktipp] {label}: Keine CSV im ZIP")
                            return []
                        text = zf.read(csv_files[0]).decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
                        print(f"[Kicktipp] {label}: CSV '{csv_files[0]}' entpackt")
                    else:
                        text = r2.text.replace('\r\n', '\n').replace('\r', '\n')

                    if ";" in text[:500] and "<html" not in text[:200].lower():
                        rows = list(csv.DictReader(io.StringIO(text), delimiter=";", quotechar='"'))
                        print(f"[Kicktipp] {label} CSV: {len(rows)} Zeilen, Spalten: {list(rows[0].keys()) if rows else []}")
                        return rows
                    else:
                        print(f"[Kicktipp] {label} kein CSV: {r2.text[:100]}")
                except requests.exceptions.Timeout:
                    print(f"[Kicktipp] {label} Timeout nach 15s")
                except Exception as e:
                    print(f"[Kicktipp] {label} Fehler: {e}")
                    traceback.print_exc()
                return []

            # Liste aller Tipper → Wert laut Kicktipp-Dropdown: "tipperliste"
            rows_tipper = do_export("tipperliste", "Liste aller Tipper")
            if rows_tipper:
                results["tipper"] = rows_tipper

            # Rangliste → "ranking" mit spieltagIndex=0 für Gesamtrangliste
            rows_rangliste = do_export("ranking", "Rangliste", {"tippspieltagIndex": "0"})
            if not rows_rangliste:
                # Fallback: gesamtuebersicht probieren
                rows_rangliste = do_export("gesamtuebersicht", "Gesamtübersicht", {"tippspieltagIndex": "0", "wertung": "einzelwertung"})
            if rows_rangliste:
                results["rangliste"] = rows_rangliste

        except Exception as e:
            print(f"[Kicktipp] Datenexport Fehler: {e}")
            traceback.print_exc()

        return results
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
    def parse_exports(exports: dict) -> tuple:
        """
        Verarbeitet die CSV-Exporte.
        exports = {"tipper": [...], "rangliste": [...]}
        Gibt zurück: (rangliste_dict, tipper_namen_list)
        """
        tipper_namen = []
        rangliste    = {}

        # Teilnehmernamen aus "Liste aller Tipper"
        tipper_rows = exports.get("tipper", [])
        if tipper_rows:
            name_col = next((k for k in tipper_rows[0].keys()
                             if "name" in k.lower() or "tipper" in k.lower()), None)
            if not name_col and tipper_rows[0]:
                name_col = list(tipper_rows[0].keys())[0]
            print(f"[Parse] Tipper-Spalte: '{name_col}', Spalten: {list(tipper_rows[0].keys())}")
            tipper_namen = [r.get(name_col,"").strip() for r in tipper_rows
                            if r.get(name_col,"").strip()]
            print(f"[Parse] {len(tipper_namen)} Tipper: {tipper_namen}")

        # Rangliste aus "Rangliste"-Export
        rl_rows = exports.get("rangliste", [])
        if rl_rows:
            header = list(rl_rows[0].keys())
            print(f"[Parse] Rangliste-Spalten: {header}")
            spieltag_cols = [k for k in header
                             if "spieltag" in k.lower()
                             and "gesamt" not in k.lower()
                             and "siege" not in k.lower()]
            name_col      = next((k for k in header if k.lower() in ("name","tipper","benutzername")), None)
            if not name_col:
                name_col = next((k for k in header if "name" in k.lower()), None)
            print(f"[Parse] Name-Spalte: '{name_col}', Spieltag-Spalten: {spieltag_cols}")

            if name_col and spieltag_cols:
                for st_idx, col in enumerate(spieltag_cols, start=1):
                    st_data = []
                    for row in rl_rows:
                        name = str(row.get(name_col, "")).strip()
                        if not name:
                            continue
                        kumuliert = sum(
                            int(str(row.get(c,"0")).strip())
                            if str(row.get(c,"0")).strip().lstrip("-").isdigit() else 0
                            for c in spieltag_cols[:st_idx]
                        )
                        pts_st = int(str(row.get(col,"0")).strip()) \
                            if str(row.get(col,"0")).strip().lstrip("-").isdigit() else 0
                        st_data.append({"name": name, "pts_spieltag": pts_st,
                                        "pts_gesamt": kumuliert,
                                        "rang": str(row.get("Rang","0")).strip(), "delta": 0})
                    st_data.sort(key=lambda x: x["pts_gesamt"], reverse=True)
                    if st_idx > 1 and (st_idx-1) in rangliste:
                        prev = {p["name"]: i+1 for i,p in enumerate(rangliste[st_idx-1])}
                        for i,p in enumerate(st_data):
                            p["delta"] = prev.get(p["name"], i+1) - (i+1)
                    rangliste[st_idx] = st_data
                print(f"[Parse] Rangliste: {len(rangliste)} Spieltage")
            elif name_col and not spieltag_cols:
                # Nur Gesamtpunkte-Spalte vorhanden (WM noch nicht gestartet oder nur 1 Spieltag)
                gesamt_col = next((k for k in header if "gesamt" in k.lower()), None)
                if gesamt_col:
                    rows_sorted = sorted(rl_rows,
                        key=lambda r: int(r.get(gesamt_col,"0") or "0"), reverse=True)
                    rangliste[1] = [{"name": r.get(name_col,"").strip(),
                                     "pts_spieltag": int(r.get(gesamt_col,"0") or "0"),
                                     "pts_gesamt":   int(r.get(gesamt_col,"0") or "0"),
                                     "rang": r.get("Rang","0").strip(), "delta": 0}
                                    for r in rows_sorted if r.get(name_col,"").strip()]

        return rangliste, tipper_namen

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

    # 2. CSV-Exporte von Kicktipp holen
    exports = kt.get_rangliste_csv()
    neue_rangliste, tipper_namen = KicktippScraper.parse_exports(exports)

    # Priorität für Rangliste:
    # A) Kicktipp-Export mit echten Punkten (> 0) → nehmen
    # B) Bestehende data.json wenn sie echte Namen enthält → behalten
    # C) Feste Starttabelle mit 15 bekannten Teilnehmern → immer korrekt

    FAKE_NAMEN = {"heim", "gast", "gruppe", "ergebnis", "tendenz", "de"}

    hat_echte_punkte = any(
        p.get("pts_gesamt", 0) > 0
        for st_data in neue_rangliste.values()
        for p in st_data
    )

    if hat_echte_punkte:
        rangliste = neue_rangliste
        print(f"[Rangliste] ✓ Kicktipp-Export mit echten Punkten: {len(neue_rangliste)} Spieltage")
    else:
        # Bestehende data.json prüfen
        rangliste_existing = {}
        if os.path.exists(OUTPUT_FILE):
            try:
                with open(OUTPUT_FILE, encoding="utf-8") as f:
                    existing = json.load(f)
                rangliste_existing = {int(k): v for k, v in existing.get("ranglisten", {}).items()}
            except Exception as e:
                print(f"[Rangliste] data.json lesen fehlgeschlagen: {e}")

        # Prüfen ob bestehende Rangliste echte Namen enthält
        hat_echte_namen = False
        if rangliste_existing:
            erste_liste = list(rangliste_existing.values())[0]
            echte = [p for p in erste_liste if p.get("name","").lower() not in FAKE_NAMEN]
            hat_echte_namen = len(echte) >= 5  # mind. 5 echte Namen

        if hat_echte_namen:
            rangliste = rangliste_existing
            erste = list(rangliste.values())[0]
            print(f"[Rangliste] ✓ Bestehende data.json: {len(erste)} Tipper ({erste[0]['name']} ...)")
        else:
            rangliste = {1: STARTTABELLE}
            print(f"[Rangliste] ✓ Feste Starttabelle: {len(STARTTABELLE)} Tipper")

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
    # Basis: erster Spieltag mit gestarteten Spielen laut football-data.org
    # NICHT aus rangliste.keys() — die hat alle CSV-Spalten als "Spieltage"
    aktiver_st = 1
    for st_id in sorted(spiele_by_spieltag.keys()):
        spiele = spiele_by_spieltag[st_id]
        if any(s["status"] in ("finished", "live") for s in spiele):
            aktiver_st = st_id
    print(f"[Info] Aktiver Spieltag: {aktiver_st}")

    alle_st = sorted(set(list(rangliste.keys()) + list(spiele_by_spieltag.keys())))
    spieltag_meta = [{"id":i,"label":f"Spieltag {i}",
                      "aktiv":i==aktiver_st,"zukuenftig":i>aktiver_st}
                     for i in alle_st]

    # 6. KI-Kommentare generieren (Anthropic API)
    # Bestehende Kommentare laden damit Vortage nicht neu generiert werden
    ki_kommentare = {}
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                ki_kommentare = json.load(f).get("ki_kommentare", {})
        except:
            pass

    if api_key:  # Anthropic Key wird als FOOTBALL_API_KEY nicht genutzt — eigener Key
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if anthropic_key and str(aktiver_st) not in ki_kommentare:
            print(f"[KI] Generiere Kommentar für Spieltag {aktiver_st}...")
            try:
                rl = rangliste.get(aktiver_st, [])
                fuehrender = rl[0]["name"] if rl else "—"
                fuehrender_pts = rl[0]["pts_gesamt"] if rl else 0
                letzter = rl[-1]["name"] if rl else "—"
                spiele_txt = ", ".join(
                    f"{s['heim']['name']} {s['score']} {s['gast']['name']}"
                    for s in spiele_by_spieltag.get(aktiver_st, [])
                    if s["status"] == "finished"
                )
                alle_tipper = ", ".join(
                    f"{p['name']} ({p['pts_gesamt']} Pkt)"
                    for p in rl
                )
                prompt = f"""Du bist ein hyperventilierender RTL-Sport-Kommentator beim internen gds GmbH WM Tippspiel 2026.
Analysiere Spieltag {aktiver_st} und erstelle einen tagesfrischen Kommentar.

Aktueller Stand:
- Führender: {fuehrender} mit {fuehrender_pts} Punkten
- Letzter: {letzter}
- Abgeschlossene Spiele: {spiele_txt or 'noch keine'}
- Alle Tipper: {alle_tipper}

Erstelle:
1. "headline": Dramatische Schlagzeile max. 12 Wörter, CAPS für Highlights
2. "sub": Witziger Kommentar 2-3 Sätze, gerne auf Kosten des Letzten
3. "anekdote": Echte interessante Fußball-Anekdote passend zu den Spielen
4. "ticker": Array mit 5 kurzen Ticker-Meldungen (je max. 8 Wörter)

Nur JSON, kein Markdown: {{"headline":"...","sub":"...","anekdote":"...","ticker":["...","...","...","...","..."]}}"""

                import urllib.request
                req_data = json.dumps({
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": prompt}]
                }).encode("utf-8")
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    data=req_data,
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": anthropic_key,
                        "anthropic-version": "2023-06-01",
                    }
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read())
                txt = result["content"][0]["text"]
                parsed = json.loads(txt.replace("```json","").replace("```","").strip())
                ki_kommentare[str(aktiver_st)] = parsed
                print(f"[KI] ✓ Kommentar generiert: {parsed['headline'][:50]}...")
            except Exception as e:
                print(f"[KI] Fehler: {e}")
        elif str(aktiver_st) in ki_kommentare:
            print(f"[KI] Kommentar für Spieltag {aktiver_st} bereits vorhanden — übersprungen")
        else:
            print(f"[KI] ANTHROPIC_API_KEY nicht gesetzt — kein KI-Kommentar")

    # 7. data.json schreiben
    output = {
        "meta": {
            "generiert_am": datetime.now(BERLIN).strftime("%d.%m.%Y %H:%M Uhr (CEST)"),
            "aktiver_spieltag": aktiver_st,
            "quelle": KICKTIPP_GROUP,
        },
        "spieltage":     spieltag_meta,
        "ranglisten":    {str(k): v for k,v in rangliste.items()},
        "spiele":        {str(k): v for k,v in spiele_by_spieltag.items()},
        "ki_kommentare": ki_kommentare,
    }
    with open(OUTPUT_FILE,"w",encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    n_spiele = sum(len(v) for v in spiele_by_spieltag.values())
    print(f"✓ {OUTPUT_FILE} — {len(rangliste)} Spieltag-Ranglisten, {n_spiele} Spiele, {len(ki_kommentare)} KI-Kommentare")

if __name__ == "__main__":
    main()
