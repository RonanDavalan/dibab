# Skrivagner

[English](../../README.md) | [Français](../fr-FR/README.md) | **Deutsch** | [Español](../es-ES/README.md)

Skrivagner („Schreiber“ auf Bretonisch) sammelt, analysiert und archiviert die persönlichen Verwaltungsdokumente eines Haushalts (Rechnungen, Briefe, Verträge, Bescheide von Behörden) in einer einheitlichen Ordnerstruktur und führt ein Journal über alles, was es tut. Es arbeitet souverän: Keine Daten verlassen das lokale Netz, ohne Dienst Dritter, ohne entferntes Modell, ohne Cloud. Die Sprachmodelle sind die von [Ollama](https://ollama.com/) auf Ihrem eigenen Rechner.

Lizenz: [GNU Affero General Public License Version 3](../../LICENSE).

## Was Skrivagner tut und was nicht

Es tut:

- lokale Verzeichnisse, entfernte Maschinen über `ssh` (Kopie per Fingerabdruck geprüft, Originaldateien unberührt) und Postfächer über IMAP im Lesemodus durchsuchen (Anhänge werden in einem „Sammelordner“ abgelegt; das Postfach wird nicht verändert);
- den Text extrahieren (Textebene des PDFs, sonst Lesen durch ein Bildmodell), die Verwaltungsdokumente von den übrigen trennen und sie dann nach Kategorie und Bereich (privat oder beruflich) im Konsens mehrerer Modelle einordnen;
- jedes Dokument umbenennen und in den Tresor seines Bereichs verschieben, mit zeitgestempeltem Journal und der Möglichkeit, es rückgängig zu machen (`--rollback`).

Es tut nicht:

- eine Datei bewegen, bei der es nicht sicher ist: Unsicherheit führt in einen Ordner `À_VÉRIFIER/`, nie zu einer riskanten Ablage;
- irgendetwas löschen: Es verschiebt und kopiert, es löscht nicht;
- ein Postfach oder eine entfernte Maschine verändern;
- im Hintergrund laufen: Es wird von Hand gestartet, und der Standardmodus ist die Simulation (`--dry-run`);
- einen Tresor einhängen, verschlüsseln oder synchronisieren: Das ist Ihre Sache (siehe „Grenzen“).

## Ein Werkzeug für den Haushalt

Skrivagner ist für die Verwaltung eines Haushalts gedacht, durch den Haushalt. Eine Maschine, ein Verzeichnis oder ein Mail-Konto gehört nur mit dem ausdrücklichen oder stillschweigenden Einverständnis der betroffenen Person zum Geltungsbereich; im Zweifel lassen Sie es weg. Die Software kann diese Achtung nicht garantieren: Der Administrator der Instanz verpflichtet sich dazu. Das Journal enthält Dateinamen und Absender, die schon viel verraten (ein Brief einer Gesundheitsbehörde genügt): Es liegt im Tresor, nicht daneben.

## Voraussetzungen

- Linux mit Python 3.10 oder neuer (die Tests laufen unter 3.12 und 3.13); der Code verwendet nur die Standardbibliothek;
- `findmnt` (Paket `util-linux`) und `git`;
- `pdftotext` und `pdftoppm` (Paket `poppler-utils`);
- [Ollama](https://ollama.com/) installiert und gestartet, mit mindestens einem Modell pro Rolle;
- für entfernte Maschinen: `ssh` mit einem Schlüssel, der eine Sitzung ohne Passwort öffnet;
- ein Zielverzeichnis pro Bereich, möglichst auf einem verschlüsselten Datenträger.

Unter Debian:

```bash
sudo apt install python3 python3-venv git util-linux poppler-utils openssh-client
```

Die Modelle, nach Rolle (`ocr` liest gescannte Seiten, `tri_rapide` sortiert aus, was nicht administrativ ist, `classification` ordnet ein):

```bash
ollama pull glm-ocr
ollama pull gemma3:4b
ollama pull qwen2.5:3b
ollama pull gemma4:e2b
ollama pull qwen2.5
ollama pull granite4.2:8b-Q5_K_M
ollama pull mistral-nemo:12b-instruct-2407-q6_K
```

Diese Modelle sind die der Referenzinstanz; beliebige andere genügen, man muss sie nur in `ollama.roles` nennen (weiter unten). Die Modelle der Rolle `classification` stimmen ab: Ein Dokument wird nur eingeordnet, wenn ihre Übereinstimmung `ollama.seuil_confiance` erreicht. Ollama gehört nicht zu Skrivagner und wird von diesem nie installiert.

## Installation aus den Quellen

Endgültige Ordnerstruktur (`~` ist Ihr Home-Verzeichnis; passen Sie die Pfade an Ihre Installation an):

```
~/applications/skrivagner/               das geklonte Repository
├── skrivagner.py                        der Einstiegspunkt
├── modules/                             eine Datei pro Verantwortung
│   └── langues/                         die Meldungswörterbücher: en, fr, de, es
├── docs/                                die Übersetzungen dieser README und die Handbuchseite
├── tests/                               die Tests
├── config.exemple.json                  die Beispielkonfiguration, versioniert
└── venv/                                die Python-Umgebung, in Schritt 2 angelegt
~/.config/skrivagner/config.json         Ihre Konfiguration, in Schritt 3 angelegt, nie versioniert
~/.local/state/skrivagner/               Zustand, Journal und Sitzungsberichte (Standardort)
~/Classement/Personnel/                  der Tresor des privaten Bereichs
~/Classement/Professionnel/              der Tresor des beruflichen Bereichs
```

1. Das Repository klonen:

```bash
mkdir -p ~/applications && git clone https://github.com/RonanDavalan/skrivagner.git ~/applications/skrivagner
cd ~/applications/skrivagner
```

2. Die Python-Umgebung anlegen und die Tests prüfen (erwartet: `410 passed, 6 skipped`; die 6 übersprungenen sind die Versuche gegen ein laufendes Ollama):

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q tests
```

3. Die Konfiguration mit Modus `600` anlegen. Skrivagner liest die erste gefundene Datei aus: der Option `--config <Pfad>`, der Umgebungsvariablen `SKRIVAGNER_CONFIG`, `~/.config/skrivagner/config.json` (oder `$XDG_CONFIG_HOME/skrivagner/config.json`), dann `config.json` neben `skrivagner.py`. Eine Option oder Variable, die auf eine fehlende Datei zeigt, beendet das Programm: Es fällt nie auf eine andere Datei zurück.

```bash
mkdir -p ~/.config/skrivagner
cp config.exemple.json ~/.config/skrivagner/config.json
chmod 600 ~/.config/skrivagner/config.json
```

4. Die beiden Tresore anlegen und den Typ ihres Dateisystems lesen:

```bash
mkdir -p ~/Classement/Personnel ~/Classement/Professionnel
findmnt -n -T ~/Classement/Personnel -o FSTYPE
```

Der Befehl gibt zum Beispiel `ext4` aus. Vor jedem Schreiben beweist Skrivagner, dass die Wurzel jedes Tresors eingehängt ist, denn ein geschlossener Tresor hinterlässt einen nackten Ordner unverschlüsselt auf der Platte: Es vergleicht diesen Typ mit `systemes_fichiers_acceptes`. Das Beispiel erwartet `fuse.gocryptfs`. Wenn Sie anders verschlüsseln (LUKS, eCryptfs …), öffnen Sie den Datenträger und tragen Sie den Typ ein, den `findmnt` für ihn liefert. Auf einem unverschlüsselten Datenträger unterscheidet diese Prüfung ein fehlendes von einem vorhandenen Einhängen nicht mehr: Sie verzichten dann auf diesen Schutz.

5. `~/.config/skrivagner/config.json` bearbeiten, mindestens diese Schlüssel:

| Schlüssel | Aufgabe |
|---|---|
| `destinations.personnel.racine` und `destinations.professionnel.racine` | die beiden Tresore, hier `~/Classement/Personnel` und `~/Classement/Professionnel` |
| `destinations.*.systemes_fichiers_acceptes` | der in Schritt 4 gelesene Typ |
| `personnes` | die Vornamen des Haushalts, die die Ordner des privaten Bereichs benennen |
| `sources_locales[].chemin` | die zu durchsuchenden Verzeichnisse |
| `suivi.fichier_date`, `suivi.journal`, `suivi.sessions` | fehlen sie, wird der Zustand unverschlüsselt unter `~/.local/state/skrivagner/` (oder `$XDG_STATE_HOME/skrivagner/`) geschrieben; um ihn zu verschlüsseln, tragen Sie diese drei Schlüssel im Tresor ein (zum Beispiel `~/Classement/Personnel/logs/…`): Das Journal enthält sensible Daten |
| `ollama.roles` | für jede Rolle die bevorzugten Modelle der Reihe nach; das erste installierte wird verwendet |

Die vollständige Liste der Schlüssel und ihrer Wirkung steht in `config.exemple.json`, dessen Blöcke jeweils ein realistisches Beispiel sind. Passwörter gehören nie hinein.

6. Die Installation prüfen, ohne etwas zu schreiben:

```bash
venv/bin/python skrivagner.py --version
venv/bin/python skrivagner.py --diagnose
```

`--version` schreibt eine Zeile und endet:

```
skrivagner 0.9.0-alpha
```

`--diagnose` schreibt eine Zeile pro Prüfung, `<ZUSTAND> <Kennung> : <Meldung>`, dann eine Zusammenfassung. In einem neuen Home-Verzeichnis, ohne Konfiguration und ohne Ollama, lautet die Ausgabe wie folgt, und der Exit-Code ist `0`:

```
OK python : 3.13.5
OK outil_pdftotext : /usr/bin/pdftotext
OK outil_pdftoppm : /usr/bin/pdftoppm
OK outil_findmnt : /usr/bin/findmnt
OK outil_ssh : /usr/bin/ssh
NON_CONFIGURÉ configuration : keine Konfiguration gefunden (die Option --config: nicht angegeben; die Variable SKRIVAGNER_CONFIG: nicht angegeben; der XDG-Ort: ~/.config/skrivagner/config.json; der Ordner des Skripts: ~/applications/skrivagner/config.json)
NON_VÉRIFIÉ emplacement_etat : hängt von der Konfiguration ab
NON_VÉRIFIÉ ollama : hängt von der Konfiguration ab
NON_VÉRIFIÉ modele_ocr : hängt von der Konfiguration ab
NON_VÉRIFIÉ modele_tri_rapide : hängt von der Konfiguration ab
NON_VÉRIFIÉ modele_classification : hängt von der Konfiguration ab
NON_VÉRIFIÉ destination_personnel : hängt von der Konfiguration ab
NON_VÉRIFIÉ destination_professionnel : hängt von der Konfiguration ab
Diagnose: 5 OK, 0 Warnung(en), 0 Fehler, 1 nicht konfiguriert, 7 nicht geprüft
```

Die Zustandskürzel (`OK`, `AVERTISSEMENT`, `ÉCHEC`, `NON_CONFIGURÉ`, `NON_VÉRIFIÉ`) und die Kennungen sind in allen Sprachen gleich, damit ein Skript sie vergleichen kann. Sobald die Konfiguration geschrieben ist, ist alles, was sie deklariert und die Maschine nicht erfüllt (Ollama aus, Modell fehlt, Tresor nicht eingehängt), ein `ÉCHEC`, und der Exit-Code ist `1`. Mit der ausgefüllten Konfiguration aus Schritt 5 und eingehängten Tresoren endet die Ausgabe mit einer Zusammenfassung wie dieser:

```
Diagnose: 12 OK, 1 Warnung(en), 0 Fehler, 0 nicht konfiguriert, 0 nicht geprüft
```

Die einzige Warnung betrifft Zustand und Journal, die unverschlüsselt unter `~/.local/state/skrivagner/` liegen, bis Sie sie in einen Tresor verlegen.

## Sprache der Meldungen

Skrivagner schreibt seine Meldungen auf Englisch, Französisch, Deutsch oder Spanisch. Die Sprache wird einmal beim Start gelesen, aus der ersten nicht leeren der Variablen `LC_ALL`, `LC_MESSAGES` und `LANG`: `fr_FR.UTF-8` ergibt Französisch, `de_DE.UTF-8` Deutsch, `es_ES.UTF-8` Spanisch, `en_US.UTF-8` Englisch, jeder andere Wert oder keiner Englisch. Um dieselbe Prüfung in einer anderen Sprache zu lesen:

```bash
LC_ALL=fr_FR.UTF-8 venv/bin/python skrivagner.py --diagnose
```

Optionsnamen, Zustandskürzel, Kennungen, Journale und Plandateien ändern sich nie mit der Sprache: Was auf die Platte geschrieben wird, ist Englisch, damit ein in einer Sprache geschriebenes Journal von `--rollback` in jeder anderen wieder abgespielt wird. Die Meldungswörterbücher sind die Dateien `modules/langues/en.txt`, `fr.txt`, `de.txt` und `es.txt`.

## Verwendung

```bash
cd ~/applications/skrivagner
venv/bin/python skrivagner.py --dry-run     # Simulation (Standard): nichts bewegt sich
venv/bin/python skrivagner.py --execute     # tatsächliche Ablage
venv/bin/python skrivagner.py --rollback    # macht die letzte Ablagesitzung rückgängig
venv/bin/python skrivagner.py --inventaire  # liest den Bestand der Tresore, nichts wird verschoben
venv/bin/python skrivagner.py --diagnose    # prüft Installation, Konfiguration, Ollama und Tresore, schreibt nichts
venv/bin/python skrivagner.py --version     # schreibt eine Zeile, `skrivagner <Version>`, und endet
venv/bin/python skrivagner.py --dry-run --config ~/andere/config.json   # liest jene Konfiguration
venv/bin/python skrivagner.py --help        # listet alle Optionen, in der Sprache der Sitzung
```

Beginnen Sie immer mit `--dry-run`, prüfen Sie jedes vorgeschlagene Ziel und starten Sie dann `--execute`. Der erste Durchlauf ist langsam (mehrere Modelle lesen jedes Dokument); die Fehlerausgabe zeigt den Fortschritt, `Modell i/n, Dokument j/m`. Hier ein `--dry-run` auf einem leeren Quellordner, der Ollama und die drei Modelle der Rollen voraussetzt:

```
Skrivagner 0.9.0-alpha — Sitzung 2026-10-29T17:18:29
  Modus              : dry-run
  Konfiguration      : ~/.config/skrivagner/config.json
  Tresor personnel     : ~/Classement/Personnel — eingehängt
  Tresor professionnel : ~/Classement/Professionnel — eingehängt
  Sitzungsjournal    : ~/.local/state/skrivagner/sessions/session_2026-10-29T17:18:29.jsonl
  Modell ocr           : glm-ocr:latest
  Modell tri_rapide    : gemma3:4b
  Modell classification: granite4.2:8b-Q5_K_M
  Konsens            : 1 Klassifikationsmodell(e), Schwelle 0.4

Quelle: entrant (~/Classement/Entrant)
  (keine Datei als Kandidat)
  Summe Quelle: 0 Datei(en), 0 B

============================================================
Summe Scan: 0 Kandidatendatei(en), 0 B
============================================================
Textextraktion (der Text wird weder angezeigt noch geschrieben)

Klassifikation (Dry-Run, nichts wird verschoben; der Text wird weder angezeigt noch geschrieben)
```

Exit-Codes:

| Code | Bedeutung |
|---|---|
| `0` | Erfolg |
| `1` | Konfiguration nicht gefunden, ungültig oder mit fehlendem Schlüssel; mindestens eine Quelle oder ein Dokument fehlgeschlagen; Rollback nur teilweise; OAuth2-Einwilligung fehlgeschlagen; `--diagnose` mit mindestens einem `ÉCHEC` |
| `2` | Tresor vor einem schreibenden Modus nicht als eingehängt nachgewiesen; ungültige Befehlszeile |
| `3` | kein Modell für eine Rolle installiert (`ollama list`), oder Ollama antwortet nicht |
| `4` | `--execute` auf dieser Maschine abgelehnt (Schlüssel `executer_sur`) |
| `5` | ein anderer Lauf hält die Sperre `skrivagner.verrou` (neben `suivi.fichier_date`) |

Jede Verschiebung wird im Aktionsjournal festgehalten (`suivi.journal`, eine JSON-Zeile pro Aktion, ohne Dokumenttext), und jede Sitzung hinterlässt einen Bericht in `suivi.sessions`. `--rollback --session <Zeitstempel>` macht eine bestimmte Sitzung rückgängig: Das Dokument kehrt an seinen ursprünglichen Platz zurück, die Kopie per Fingerabdruck geprüft.

### Handbuchseite

Die Handbuchseite ist in Markdown in `docs/skrivagner.1.md` geschrieben, ihre Übersetzungen liegen in `docs/fr-FR/`, `docs/de-DE/` und `docs/es-ES/`. Um sie aus den Quellen zu lesen:

```bash
pandoc --standalone --from markdown-smart --to man docs/de-DE/skrivagner.1.md | man -l -
```

### Entfernte Maschinen über ssh

Deklarieren Sie jede Maschine in `sources_distantes` (`ssh`-Alias, Verzeichnisse, `vide_poches_destination`). `ssh <Alias> true` muss ohne Passwort gelingen, und die Maschine muss `find`, `sha256sum` und `cat` anbieten. In der Simulation listet Skrivagner die Dateien auf, ohne etwas zu kopieren; bei der Ausführung kopiert es sie in den Sammelordner der Maschine, prüft ihren Fingerabdruck und behandelt sie dann wie lokale Dateien. Die Originaldateien bleiben unberührt. Eine abgelehnte Verbindung beendet die betroffene Maschine: Versuchen Sie es nicht in einer Schleife erneut.

### Postfächer über IMAP

Deklarieren Sie jedes Postfach in `sources_imap`. Das Passwort wird aus der Umgebungsvariablen gelesen, die `mot_de_passe_env` nennt, nie aus der Datei:

```bash
read -rs SKRIVAGNER_IMAP_EXEMPLE && export SKRIVAGNER_IMAP_EXEMPLE
```

Skrivagner öffnet die Ordner schreibgeschützt (`EXAMINE`) und liest nur den Anhang (`BODY.PEEK`): Keine Nachricht wird als gelesen markiert, kein Flag gesetzt.

### Google-Konten über OAuth2

Ein Google-Konto wird statt mit dem Passwort mit einem OAuth2-Token abgerufen (`AUTHENTICATE XOAUTH2`). In der [Google-Cloud-Konsole](https://console.cloud.google.com), mit dem abzurufenden Konto: ein Projekt anlegen, die Gmail-API aktivieren, den OAuth-Zustimmungsbildschirm konfigurieren (Typ extern), ihn dann **veröffentlichen** (Status „In production“, denn unter „Testing“ läuft die Autorisierung nach sieben Tagen ab), schließlich einen Berechtigungsnachweis „Desktop-App“ anlegen und dessen JSON herunterladen. Legen Sie es im Tresor ab, mit Modus `600`, deklarieren Sie dann die Quelle mit `"authentification": "oauth2"`, `client_fichier` und `token_fichier` (siehe das Beispiel `imap-google-exemple`) und stimmen Sie einmalig zu:

```bash
venv/bin/python skrivagner.py --autoriser-google imap-google-exemple
```

Öffnen Sie die angezeigte Adresse in einem Browser, akzeptieren Sie die Warnung „nicht verifizierte App“ (es ist Ihre eigene Anwendung) und die Einwilligung. Das Token wird mit Modus `600` im Ordner des `token_fichier` geschrieben, der ein Git-Repository und die Pfade aus `oauth2.chemins_interdits` ablehnt; es erneuert sich selbst und erscheint weder im Journal noch auf dem Bildschirm. Widerruft Google es (Zugriff entzogen, Kontopasswort geändert, sechs Monate ohne Scan), endet Skrivagner mit einer eindeutigen Meldung: Führen Sie den Befehl erneut aus.

## Souveränität

- Die Aufrufe an Ollama sind HTTP-Anfragen an `ollama.url` (standardmäßig `http://localhost:11434`); kein Dokument und kein Dateiname geht anderswohin.
- Die einzigen externen Dienste, die der Code erreichen kann, sind die von Ihnen deklarierten: Ihre Maschinen über `ssh`, Ihre IMAP-Postfächer und, falls Sie OAuth2 aktivieren, die Autorisierungsendpunkte von Google.
- Kein Geheimnis wird in `config.json` gespeichert: Passwörter in einer Umgebungsvariablen, Token in `600`-Dateien außerhalb jedes Repositorys.

## Grenzen

- Nur Linux. Die Einhängeprüfung beruht auf `findmnt`.
- Die Einordnung ist so gut wie Ihre Modelle: Auf der Referenzinstanz hat ein erster Versuch mit 15 echten Dokumenten 2 eingeordnet, 3 als nicht administrativ ausgesondert und 10 aus Vorsicht in `À_VÉRIFIER/` gelegt. Messen Sie, bevor Sie vertrauen: Die Messung des Bereichs liegt in `_outils/mesurer_domaines.py`.
- Skrivagner hängt keinen Tresor ein, verschlüsselt und synchronisiert keinen und löscht nichts: Speicherplatz und Sicherungen liegen in Ihrer Verantwortung.
- Die Kategorien, die bekannten Absender und die Namensvorlage in `config.exemple.json` spiegeln das französische Verwaltungsleben wider (Familienkasse, Finanzamt, Versicherungen); passen Sie sie an Ihr Land an.
- Die Schritte in der Google-Konsole hängen von Googles Oberfläche ab, die sich ändert: Die Begriffe bleiben die seiner OAuth2-Dokumentation.
- Das Projekt ist jung: Version 0.9.0-alpha, keine kontinuierliche Integration.

## Beitragen, eine Sicherheitslücke melden

Siehe [CONTRIBUTING.md](../../CONTRIBUTING.md). Eine Sicherheitslücke wird privat gemäß [SECURITY.md](../../SECURITY.md) gemeldet, nie in einem öffentlichen Ticket.

## Mitwirkende

Skrivagner ist das Ergebnis einer Zusammenarbeit zwischen einer Person und Sprachmodellen, mit den Rollen so aufgeschrieben, wie sie gespielt wurden. Die vollständige Liste steht in [CONTRIBUTORS.md](../../CONTRIBUTORS.md).

*   **Ronan Davalan**: Architekt und Schiedsrichter; Vision, Entscheidungen, Umfang, Freigabe. Einziger Git-Autor.
*   **Claude Code (Anthropic)**: Umsetzungsingenieur; Python-Code und Tests sowie die öffentlichen Dokumente (diese README und ihre Übersetzungen, die Handbuchseite, `CONTRIBUTING.md`, `SECURITY.md`).
*   **Gemini (Google)**: Entwurfsberater; schlug den ursprünglichen Namen „Le Greffier“ vor.
*   **Copilot (Microsoft)**: übersetzte diesen Namen ins Bretonische, daher „Skrivagner“.
