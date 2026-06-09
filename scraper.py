"""
gds WM Tippspiel 2026 — Datenscraper
=====================================
Läuft täglich via GitHub Actions.
Holt Daten von zwei Quellen:
  1. Kicktipp (Login + CSV-Export der Gesamtübersicht)
  2. football-data.org (echte Spielergebnisse WM 2026)
Schreibt das Ergebnis als data.json ins Repo.

Umgebungsvariablen (GitHub Secrets):
  KICKTIPP_EMAIL     — deine Kicktipp-Login-E-Mail
  KICKTIPP_PASSWORD  — dein Kicktipp-Passwort
  FOOTBALL_API_KEY   — kostenloser API-Key von football-data.org
"""

import os
import json
import csv
import io
import time
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup


# ─── KONFIGURATION ────────────────────────────────────────────
KICKTIPP_BASE       = "https://www.kicktipp.de"
KICKTIPP_GROUP      = "gds-wm-tippspiel2026"
FOOTBALL_API_BASE   = "https://api.football-data.org/v4"
WM_COMPETITION_CODE = "WC"   # football-data.org Code für FIFA WM
OUTPUT_FILE         = "data.json"


# ─── KICKTIPP SCRAPER ──────────────────────────────────────────
class KicktippScraper:
    def __init__(self, email: str, password: str):
        self.email    = email
        self.password = password
        self.session  = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        })

    def login(self) -> bool:
        """Kicktipp-Login via Formular."""
        print("[Kicktipp] Versuche Login...")
        r = self.session.get(f"{KICKTIPP_BASE}/info/login")
        soup = BeautifulSoup(r.text, "html.parser")

        # CSRF-Token aus dem Login-Formular holen
        token_input = soup.find("input", {"name": "_token"}) or \
                      soup.find("input", {"name": "csrf_token"}) or \
                      soup.find("input", {"type": "hidden"})
        token = token_input["value"] if token_input else ""

        payload = {
            "login_email":    self.email,
            "login_password": self.password,
            "_token":         token,
        }
        r = self.session.post(
            f"{KICKTIPP_BASE}/info/login",
            data=payload,
            allow_redirects=True
        )

        if "logout" in r.text.lower() or r.url != f"{KICKTIPP_BASE}/info/login":
            print("[Kicktipp] Login erfolgreich.")
            return True
        print("[Kicktipp] Login fehlgeschlagen — Credentials prüfen!")
        return False

    def get_rangliste_csv(self) -> list[dict]:
        """
        Lädt den CSV-Export 'Gesamtübersicht Einzelwertung'.
        Das ist exakt der Export den du manuell kennst:
        Rang;Name;1. Spieltag;2. Spieltag;...;Gesamtpunkte
        """
        print("[Kicktipp] Lade Ranglisten-CSV...")

        # Spielleiter-Bereich: Datenexport aufrufen
        export_url = (
            f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/datenexport/rangliste"
            f"?typ=gesamtuebersicht&wertung=einzelwertung"
        )
        r = self.session.get(export_url)

        if r.status_code != 200:
            print(f"[Kicktipp] CSV-Export fehlgeschlagen: HTTP {r.status_code}")
            # Fallback: Seite scrapen statt CSV
            return self._scrape_rangliste_fallback()

        # CSV parsen (Semikolon-getrennt, Anführungszeichen)
        reader = csv.DictReader(
            io.StringIO(r.text),
            delimiter=";",
            quotechar='"'
        )
        rows = []
        for row in reader:
            rows.append(row)

        print(f"[Kicktipp] {len(rows)} Tipper geladen.")
        return rows

    def _scrape_rangliste_fallback(self) -> list[dict]:
        """
        Fallback: Rangliste direkt von der Tabellenansicht scrapen
        falls der CSV-Export nicht funktioniert.
        """
        print("[Kicktipp] Fallback: Scrape Rangliste-Seite...")
        r = self.session.get(f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/rangliste")
        soup = BeautifulSoup(r.text, "html.parser")
        rows = []
        table = soup.find("table", class_="rangliste") or soup.find("table")
        if not table:
            return []
        for tr in table.find_all("tr")[1:]:
            tds = tr.find_all("td")
            if len(tds) >= 3:
                rows.append({
                    "Rang":           tds[0].get_text(strip=True),
                    "Name":           tds[1].get_text(strip=True),
                    "Gesamtpunkte":   tds[-1].get_text(strip=True),
                })
        return rows

    def get_spieltag_tipps(self, spieltag: int) -> list[dict]:
        """
        Holt die Tipps aller Tipper für einen bestimmten Spieltag.
        Scrapt die Tippübersicht-Seite.
        """
        print(f"[Kicktipp] Lade Tipps Spieltag {spieltag}...")
        url = f"{KICKTIPP_BASE}/{KICKTIPP_GROUP}/tippuebersicht?spieltagIndex={spieltag - 1}"
        r = self.session.get(url)
        soup = BeautifulSoup(r.text, "html.parser")
        tipps = []

        # Spiel-Blöcke parsen
        spiel_rows = soup.find_all("tr", class_=lambda c: c and "tippreihe" in c)
        for row in spiel_rows:
            # Heimteam / Gastteam aus Header davor holen
            # Tipps der einzelnen User
            cells = row.find_all("td")
            for cell in cells:
                name_el = cell.find(class_="tippname")
                tipp_el = cell.find(class_="tipp")
                if name_el and tipp_el:
                    tipps.append({
                        "name": name_el.get_text(strip=True),
                        "tipp": tipp_el.get_text(strip=True),
                    })

        return tipps

    @staticmethod
    def parse_rangliste_csv(rows: list[dict]) -> dict:
        """
        Wandelt die CSV-Zeilen in eine strukturierte Rangliste um.
        Erkennt alle Spieltag-Spalten automatisch.
        Gibt zurück: { spieltag_id: [{name, pts, cumulative_pts}, ...] }
        """
        if not rows:
            return {}

        # Spaltenname aller Spieltage ermitteln
        spieltag_cols = [k for k in rows[0].keys()
                         if "spieltag" in k.lower() or "Spieltag" in k]

        result = {}

        for st_idx, col in enumerate(spieltag_cols, start=1):
            st_data = []
            for row in rows:
                pts_str = row.get(col, "").strip()
                pts = int(pts_str) if pts_str.isdigit() else 0
                # Gesamtpunkte bis zu diesem Spieltag aufaddieren
                cumulative = 0
                for prev_col in spieltag_cols[:st_idx]:
                    v = row.get(prev_col, "").strip()
                    cumulative += int(v) if v.isdigit() else 0
                st_data.append({
                    "name":           row.get("Name", "").strip(),
                    "pts_spieltag":   pts,
                    "pts_gesamt":     cumulative,
                    "rang":           row.get("Rang", "0").strip(),
                })

            # Nach Gesamtpunkten sortieren
            st_data.sort(key=lambda x: x["pts_gesamt"], reverse=True)

            # Platzveränderung berechnen (vs. Vorspielgtag)
            if st_idx > 1 and (st_idx - 1) in result:
                prev = {p["name"]: i + 1
                        for i, p in enumerate(result[st_idx - 1])}
                for i, p in enumerate(st_data):
                    prev_rank = prev.get(p["name"], i + 1)
                    p["delta"] = prev_rank - (i + 1)
            else:
                for p in st_data:
                    p["delta"] = 0

            result[st_idx] = st_data

        return result


# ─── FOOTBALL-DATA.ORG API ─────────────────────────────────────
class FootballAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"X-Auth-Token": api_key})

    def get_wm_matches(self) -> list[dict]:
        """Holt alle WM 2026 Spiele (inkl. Live-Status)."""
        print("[Football-API] Lade WM-Spiele...")
        url = f"{FOOTBALL_API_BASE}/competitions/{WM_COMPETITION_CODE}/matches"
        r   = self.session.get(url)

        if r.status_code == 429:
            print("[Football-API] Rate limit — 60s warten...")
            time.sleep(60)
            r = self.session.get(url)

        if r.status_code != 200:
            print(f"[Football-API] Fehler: HTTP {r.status_code}")
            return []

        data    = r.json()
        matches = data.get("matches", [])
        print(f"[Football-API] {len(matches)} Spiele geladen.")
        return matches

    @staticmethod
    def parse_matches(matches: list[dict]) -> dict:
        """
        Wandelt die API-Antwort in eine spieltag-gruppierte Struktur um.
        Gibt zurück: { spieltag_id: [{ heim, gast, score, status, zeit }, ...] }
        """
        by_spieltag = {}

        for m in matches:
            md  = m.get("matchday")
            if md is None:
                continue

            # Spielstatus normalisieren
            status_raw = m.get("status", "SCHEDULED")
            if status_raw in ("FINISHED",):
                status = "finished"
            elif status_raw in ("IN_PLAY", "PAUSED", "HALF_TIME"):
                status = "live"
            else:
                status = "upcoming"

            # Ergebnis
            score_data = m.get("score", {})
            full_time  = score_data.get("fullTime", {})
            ht_score   = score_data.get("halfTime", {})
            home_goals = full_time.get("home")
            away_goals = full_time.get("away")

            if status == "finished" and home_goals is not None:
                score = f"{home_goals}:{away_goals}"
            elif status == "live":
                in_play = score_data.get("fullTime", {})
                h = in_play.get("home", 0) or 0
                a = in_play.get("away", 0) or 0
                score = f"{h}:{a}"
            else:
                score = "—"

            # Uhrzeit
            utc_date = m.get("utcDate", "")
            try:
                dt  = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
                # In CET/CEST umrechnen (UTC+1/+2)
                import zoneinfo
                cet = zoneinfo.ZoneInfo("Europe/Berlin")
                dt_local = dt.astimezone(cet)
                zeit_str = dt_local.strftime("%H:%M")
                if status == "finished":
                    zeit_str = "Abpfiff"
            except Exception:
                zeit_str = utc_date[:10]

            # Minutenanzeige bei Live-Spielen (API liefert keine Spielminute direkt)
            if status == "live":
                zeit_str = "LIVE"

            # Länder-Flaggen-Mapping (Auswahl WM-Teilnehmer)
            FLAG_MAP = {
                "Mexico": "🇲🇽", "Canada": "🇨🇦", "United States": "🇺🇸",
                "Brazil": "🇧🇷", "Argentina": "🇦🇷", "Germany": "🇩🇪",
                "France": "🇫🇷", "Spain": "🇪🇸", "Portugal": "🇵🇹",
                "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Netherlands": "🇳🇱", "Belgium": "🇧🇪",
                "Uruguay": "🇺🇾", "Colombia": "🇨🇴", "Chile": "🇨🇱",
                "Japan": "🇯🇵", "South Korea": "🇰🇷", "Australia": "🇦🇺",
                "Morocco": "🇲🇦", "Senegal": "🇸🇳", "Nigeria": "🇳🇬",
                "Saudi Arabia": "🇸🇦", "Iran": "🇮🇷", "Japan": "🇯🇵",
                "Switzerland": "🇨🇭", "Croatia": "🇭🇷", "Denmark": "🇩🇰",
                "Poland": "🇵🇱", "Serbia": "🇷🇸", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
                "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "Ecuador": "🇪🇨", "Qatar": "🇶🇦",
                "Ghana": "🇬🇭", "Cameroon": "🇨🇲", "Tunisia": "🇹🇳",
                "Costa Rica": "🇨🇷", "Panama": "🇵🇦", "Honduras": "🇭🇳",
                "Jamaica": "🇯🇲", "Peru": "🇵🇪", "Venezuela": "🇻🇪",
                "Indonesia": "🇮🇩", "New Zealand": "🇳🇿",
            }

            heim_name = m.get("homeTeam", {}).get("name", "")
            gast_name = m.get("awayTeam", {}).get("name", "")

            spiel = {
                "heim": {
                    "name": heim_name,
                    "flag": FLAG_MAP.get(heim_name, "🏳️"),
                },
                "gast": {
                    "name": gast_name,
                    "flag": FLAG_MAP.get(gast_name, "🏳️"),
                },
                "score":  score,
                "status": status,
                "zeit":   zeit_str,
                "tipps":  [],   # Wird durch Kicktipp-Daten befüllt
            }

            by_spieltag.setdefault(md, []).append(spiel)

        return by_spieltag


# ─── HAUPTPROGRAMM ─────────────────────────────────────────────
def main():
    email    = os.environ.get("KICKTIPP_EMAIL", "")
    password = os.environ.get("KICKTIPP_PASSWORD", "")
    api_key  = os.environ.get("FOOTBALL_API_KEY", "")

    if not email or not password:
        print("FEHLER: KICKTIPP_EMAIL und KICKTIPP_PASSWORD müssen gesetzt sein!")
        raise SystemExit(1)
    if not api_key:
        print("WARNUNG: FOOTBALL_API_KEY nicht gesetzt — Spielergebnisse werden leer sein.")

    # ── 1. Kicktipp-Login & Rangliste ──
    kt = KicktippScraper(email, password)
    if not kt.login():
        raise SystemExit(1)

    csv_rows  = kt.get_rangliste_csv()
    rangliste = KicktippScraper.parse_rangliste_csv(csv_rows)

    # ── 2. football-data.org ──
    spiele_by_spieltag = {}
    if api_key:
        fapi   = FootballAPI(api_key)
        matches = fapi.get_wm_matches()
        spiele_by_spieltag = FootballAPI.parse_matches(matches)

    # ── 3. Aktiven Spieltag ermitteln ──
    # Der Spieltag mit dem neuesten nicht-zukünftigen Spiel
    jetzt = datetime.now(timezone.utc)
    aktiver_spieltag = 1
    for st_id, spiele in spiele_by_spieltag.items():
        for spiel in spiele:
            if spiel["status"] in ("finished", "live"):
                aktiver_spieltag = max(aktiver_spieltag, st_id)

    # ── 4. Spieltag-Metadaten aufbauen ──
    alle_spieltage = sorted(set(
        list(rangliste.keys()) + list(spiele_by_spieltag.keys())
    ))
    spieltag_meta = []
    for st_id in alle_spieltage:
        spiele = spiele_by_spieltag.get(st_id, [])
        datum_str = ""
        if spiele:
            # Erstes Spiel des Spieltags als Datum nehmen
            pass   # Datum kommt aus API, hier vereinfacht
        spieltag_meta.append({
            "id":        st_id,
            "label":     f"Spieltag {st_id}",
            "aktiv":     st_id == aktiver_spieltag,
            "zukuenftig": st_id > aktiver_spieltag,
        })

    # ── 5. Finales JSON zusammenbauen ──
    output = {
        "meta": {
            "generiert_am":    datetime.now(timezone.utc).isoformat(),
            "aktiver_spieltag": aktiver_spieltag,
            "quelle_kicktipp":  KICKTIPP_GROUP,
        },
        "spieltage":  spieltag_meta,
        "ranglisten": {str(k): v for k, v in rangliste.items()},
        "spiele":     {str(k): v for k, v in spiele_by_spieltag.items()},
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✓ {OUTPUT_FILE} geschrieben — {len(rangliste)} Spieltage Rangliste, "
          f"{sum(len(v) for v in spiele_by_spieltag.values())} Spiele.")


if __name__ == "__main__":
    main()
