% DIBAB(1) dibab | Benutzerbefehle
% Ronan Davalan
% 2026-10-29

# NAME

dibab - sammelt, analysiert und archiviert die persönlichen Verwaltungsdokumente eines Haushalts, ohne dass Daten das lokale Netz verlassen

# ÜBERSICHT

**dibab** [**\--config** *PFAD*] [**\--dry-run** | **\--execute** | **\--inventaire**]

**dibab** **\--dry-run** **\--verdicts-simules** *DATEI*

**dibab** [**\--config** *PFAD*] **\--rollback** [**\--session** *SITZUNG*]

**dibab** [**\--config** *PFAD*] **\--autoriser-google** *ID*

**dibab** [**\--config** *PFAD*] **\--diagnose**

**dibab** {**\--version** | **\--help**}

# BESCHREIBUNG

**dibab** durchsucht lokale Verzeichnisse, entfernte Maschinen über **ssh**(1) und Postfächer über IMAP im Lesemodus. Es
extrahiert den Text jedes Dokuments, sondert aus, was nicht administrativ ist, und ordnet den Rest nach Kategorie und Bereich, privat
oder beruflich, im Konsens mehrerer Sprachmodelle ein. Jedes Dokument wird umbenannt und in den Tresor seines Bereichs verschoben,
mit einem Journal, das **\--rollback** rückgängig machen kann. Es zerstört nie ein Dokument: Das Original wird erst nach einer geprüften
Kopie entfernt; es verändert nie ein Postfach oder eine entfernte Maschine und bewegt nichts, bei dem es nicht sicher ist: Zweifel führen
in einen Ordner namens *ZU_PRÜFEN*, einstellbar über `sous_repertoire_a_verifier`. Ein Dokument, dessen Fingerabdruck bereits abgelegt ist, wird nach einer Prüfung in den durch `destination.repertoire_doublon` benannten Ordner `Duplikat/` kopiert.

Die Sprachmodelle sind die von Ollama, das auf derselben Maschine läuft. Ollama und seine Modelle werden vom Benutzer getrennt von der
Ollama-Website installiert: Dibab enthält weder das eine noch die anderen. Listen Sie die Modelle mit **ollama list** auf und
tragen Sie sie, Rolle für Rolle, im Schlüssel **ollama.roles** der Konfiguration ein. Erreicht werden nur die Zieltresore, die Maschinen
und die Postfächer, die die Konfiguration nennt.

Der Standardmodus ist die Simulation. Lesen Sie das Ergebnis von **\--dry-run** immer, bevor Sie **\--execute** starten.

# OPTIONEN

**\--dry-run**
:   Simulation, Standardmodus: durchsucht, extrahiert und ordnet ein und gibt jedes Ziel aus, das es wählen würde. Nichts wird verschoben.

**\--execute**
:   Echtbetrieb: Jedes Dokument wird kopiert, per Fingerabdruck (SHA256) geprüft und dann aus seiner Quelle entfernt. Auf einer Maschine
    abgelehnt, die der Schlüssel **executer_sur** der Konfiguration nicht aufführt.

**\--inventaire**
:   Liest den Bestand der Tresore und schreibt für jeden einen Migrationsplan. Nichts wird verschoben.

**\--rollback**
:   Macht die letzte Ablagesitzung rückgängig, oder die mit **\--session** benannte. Das Dokument kehrt an seinen ursprünglichen Platz
    zurück, die Kopie per Fingerabdruck geprüft; eine Aktion, die sich nicht rückgängig machen lässt, lässt für sich alles an Ort und Stelle.

**\--session** *SITZUNG*
:   Kennung der rückgängig zu machenden Sitzung, mit **\--rollback**.

**\--autoriser-google** *ID*
:   OAuth2-Einwilligung für die in der Konfiguration unter *ID* benannte Google-IMAP-Quelle. Gibt eine Adresse aus, die in einem Browser
    zu öffnen ist, und schreibt dann die Token-Datei der Quelle.

**\--diagnose**
:   Prüft Installation, Konfiguration, Ollama und Tresore, eine Zeile pro Prüfung, und schreibt nichts.

**\--verdicts-simules** *DATEI*
:   Nur mit **\--dry-run**: eine JSON-Datei, die einen Dateinamen einem Urteil zuordnet und deren Routing ausgegeben wird.

**\--config** *PFAD*
:   Zu lesende Konfigurationsdatei (siehe **DATEIEN**).

**\--version**
:   Schreibt eine Zeile, **dibab** *Version*, und endet.

**\--help**, **-h**
:   Listet die Optionen, in der Sprache der Sitzung.

# SPRACHE

Meldungen werden auf Englisch, Französisch, Deutsch, Spanisch oder vereinfachtem Chinesisch geschrieben. Die Sprache wird einmal beim Start gelesen, aus der
ersten nicht leeren der Variablen **LC_ALL**, **LC_MESSAGES** und **LANG**: Der Teil vor dem ersten **\_**, **.** oder **@** ergibt **en**,
**fr**, **de**, **es** oder **zh**; jeder andere Wert, **C**, **POSIX** oder keine Variable ergibt Englisch. Die Optionsnamen, die Zustandskürzel
von **\--diagnose** (**OK**, **AVERTISSEMENT**, **ÉCHEC**, **NON_CONFIGURÉ**, **NON_VÉRIFIÉ**), die Kennungen der Prüfungen und die
Zeile von **\--version** ändern sich nie. Die Schlüssel, die auf die Platte geschrieben werden (Journale, Pläne, Berichte), sind feste Bezeichner
auf Französisch (**evenement**, **horodatage**), und die freien Texte dort sind Englisch, in welcher Sprache die Sitzung auch läuft; die Aktionskürzel (**classe**, **a_verifier**, **doublon**) und die
Bereichsnamen ändern sich nie.

# INSTALLATION

Unter Debian 12 und 13 sowie unter Ubuntu 22.04 und 24.04 installiert das Debian-Paket das Programm, seine Abhängigkeiten, die fünf Handbuchseiten und die Beispielkonfiguration *config.exemple.json* in */usr/share/doc/dibab/examples/*:

    sudo apt install ./dibab_*_all.deb

**sudo apt remove dibab** und **sudo apt purge dibab** löschen die Dateien des Pakets und rühren Konfiguration, Zustand, Journal und Dokumente nie an; das Purge nennt, was es zurücklässt. Stufe: Installation und Diagnose im Container validiert auf diesen vier Versionen; ein Container zeigt weder das Einhängen eines verschlüsselten Tresors noch einen Lauf mit Ihrem eigenen Ollama.

# DATEIEN

Die Konfiguration ist die erste vorhandene Datei aus der folgenden Reihenfolge, und nur diese wird gelesen:

1.  die von **\--config** benannte Datei;
2.  die von der Variablen **DIBAB_CONFIG** benannte Datei, wenn sie nicht leer ist;
3.  *$XDG_CONFIG_HOME/dibab/config.json* oder *~/.config/dibab/config.json*, wenn **XDG_CONFIG_HOME** leer oder nicht gesetzt ist;
4.  *config.json* im Ordner von *dibab.py*.

Eine Option oder Variable, die auf eine fehlende Datei zeigt, beendet das Programm mit dem Exit-Status 1: Es fällt nie auf eine
andere Datei zurück. *config.exemple.json* ist das Beispiel, im Ordner des Programms; kopieren Sie es mit Modus 600 an einen dieser Orte.

Gibt die Konfiguration die Schlüssel von **suivi** nicht an, wird der Zustand unter *$XDG_STATE_HOME/dibab/* oder
*~/.local/state/dibab/* geschrieben: *dernier_scan.json*, *journal.jsonl* (das Aktionsjournal), *sessions/* (ein Journal und ein
Bericht pro Sitzung) und *dibab.log*. *rapatries.json*, *imap_deposes.json* und die Sperre *dibab.verrou* liegen neben
*dernier_scan.json*. Die Ordner werden mit Modus 700 und die Dateien mit Modus 600 angelegt. Der Zustand liegt dann unverschlüsselt auf
der Platte: Um ihn in einem Tresor zu halten, geben Sie die Schlüssel **suivi.fichier_date**, **suivi.journal** und **suivi.sessions** an.

Die Meldungswörterbücher sind *modules/langues/en.txt*, *fr.txt*, *de.txt*, *es.txt* und *zh.txt*, im Ordner des Programms.

# UMGEBUNG

**DIBAB_CONFIG**
:   Pfad der Konfigurationsdatei.

**XDG_CONFIG_HOME**, **XDG_STATE_HOME**
:   Basisordner der Konfiguration und des Standardzustands.

**LC_ALL**, **LC_MESSAGES**, **LANG**
:   Sprache der Meldungen (siehe **SPRACHE**).

Das Passwort eines IMAP-Postfachs wird aus der Variablen gelesen, die der Schlüssel **mot_de_passe_env** seiner Quelle nennt, nie aus
der Konfigurationsdatei.

# EXIT-STATUS

**0**
:   Erfolg.

**1**
:   Konfiguration nicht gefunden, ungültig oder mit fehlendem Schlüssel; mindestens eine Quelle oder ein Dokument fehlgeschlagen;
    Rollback nur teilweise; OAuth2-Einwilligung fehlgeschlagen; **\--diagnose** mit mindestens einem **ÉCHEC**.

**2**
:   Ein Tresor vor einem schreibenden Modus nicht als eingehängt festgestellt; ungültige Befehlszeile.

**3**
:   Kein Modell für eine Rolle installiert, oder Ollama antwortet nicht.

**4**
:   **\--execute** auf dieser Maschine abgelehnt (Schlüssel **executer_sur**).

**5**
:   Ein anderer Lauf hält die Sperre *dibab.verrou*.

# BEISPIELE

Die Installation prüfen, dann simulieren, dann wirklich ablegen:

    dibab --diagnose
    dibab --dry-run
    dibab --execute

Dieselbe Prüfung auf Englisch lesen, dann die letzte Sitzung rückgängig machen:

    LC_ALL=en_US.UTF-8 dibab --diagnose
    dibab --rollback

# SIEHE AUCH

**ollama**(1), **ssh**(1), **findmnt**(8), **pdftotext**(1), **pdftoppm**(1)

Die README des Projekts beschreibt die Installation aus dem Debian-Paket und aus den Quellen, die Konfiguration, die Quellen über **ssh**, IMAP und OAuth2 für
Google sowie die Grenzen.

# LIZENZ

GNU Affero General Public License Version 3.
