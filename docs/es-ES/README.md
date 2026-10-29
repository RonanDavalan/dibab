# Skrivagner

[English](../../README.md) | [Français](../fr-FR/README.md) | [Deutsch](../de-DE/README.md) | **Español**

Skrivagner («escriba» en bretón) recopila, analiza y clasifica los documentos administrativos personales de un hogar (facturas, cartas, contratos, avisos de organismos) en un árbol normalizado, y lleva un diario de todo lo que hace. Funciona en modo soberano: ningún dato sale de la red local, sin servicio de terceros, sin modelo remoto, sin nube. Los modelos de lenguaje son los de [Ollama](https://ollama.com/), en su propia máquina.

Licencia: [GNU Affero General Public License versión 3](../../LICENSE).

## Qué hace Skrivagner y qué no hace

Hace:

- escanear directorios locales, máquinas remotas por `ssh` (copia verificada por huella, archivos originales intactos) y buzones de correo por IMAP en solo lectura (los adjuntos se depositan en una «carpeta de entrada»; el buzón no se modifica);
- extraer el texto (capa de texto del PDF o, si no hay, lectura por un modelo de visión), separar los documentos administrativos de los demás y clasificarlos por categoría y por ámbito (personal o profesional) con un consenso de varios modelos;
- renombrar y mover cada documento a la bóveda de su ámbito, con un diario con marca de tiempo y la posibilidad de deshacerlo (`--rollback`).

No hace:

- mover un archivo del que no está seguro: la duda lleva a una carpeta `À_VÉRIFIER/`, nunca a una clasificación arriesgada;
- borrar un documento: mueve y copia, no borra (solo poda sus propios diarios antiguos, capítulo «Inventario y rotación» del manual);
- modificar un buzón de correo ni una máquina remota;
- ejecutarse en segundo plano: se lanza a mano, y el modo por defecto es la simulación (`--dry-run`);
- montar, cifrar o sincronizar una bóveda: eso corre por su cuenta (véase «Límites»).

## Una herramienta de hogar

Skrivagner está pensado para la gestión administrativa de un hogar, por el hogar. Una máquina, un directorio o una cuenta de correo solo entra en el ámbito con el acuerdo, explícito o implícito, de la persona afectada; en caso de duda, no lo incluya. El programa no puede garantizar este respeto: es el administrador de la instancia quien se compromete a ello. El diario contiene nombres de archivo y remitentes, que ya revelan mucho (basta una carta de un organismo de salud): vive en la bóveda, no a su lado.

## Requisitos

- Linux con Python 3.10 o superior (las pruebas pasan en 3.12 y 3.13); el código solo usa la biblioteca estándar;
- `findmnt` (paquete `util-linux`) y `git`;
- `pdftotext` y `pdftoppm` (paquete `poppler-utils`);
- [Ollama](https://ollama.com/) instalado y en marcha, con al menos un modelo por rol;
- para las máquinas remotas: `ssh` con una clave que abra sesión sin contraseña;
- un directorio de destino por ámbito, preferiblemente en un volumen cifrado.

En Debian:

```bash
sudo apt install python3 python3-venv git util-linux poppler-utils openssh-client
```

Los modelos, por rol (`ocr` lee las páginas escaneadas, `tri_rapide` aparta lo que no es administrativo, `classification` clasifica):

```bash
ollama pull glm-ocr
ollama pull gemma3:4b
ollama pull qwen2.5:3b
ollama pull gemma4:e2b
ollama pull qwen2.5
ollama pull granite4.2:8b-Q5_K_M
ollama pull mistral-nemo:12b-instruct-2407-q6_K
```

Estos modelos son los de la instancia de referencia; sirven otros cualesquiera, basta con nombrarlos en `ollama.roles` (más abajo). Los modelos del rol `classification` votan: un documento solo se clasifica si su acuerdo alcanza `ollama.seuil_confiance`. Ollama no forma parte de Skrivagner y este nunca lo instala.

## Instalación desde el paquete Debian

En Debian 12 y 13 y en Ubuntu 22.04 y 24.04, un solo archivo instala el programa y sus dependencias (`python3`, `poppler-utils`, `util-linux`, `openssh-client`). No contiene ni Ollama, ni un modelo, ni una configuración. Descargue `skrivagner_*_all.deb` desde la página de descarga de [skrivagner.davalan.fr](https://skrivagner.davalan.fr/) y, desde la carpeta que lo contiene, ejecute:

```bash
sudo apt install ./skrivagner_*_all.deb
```

Cree la configuración a partir del ejemplo que instala el paquete, con el modo `600`, y siga luego los pasos 4 y 5 de la instalación desde las fuentes que figura más abajo (la bóveda de cada dominio, las claves de la configuración):

```bash
mkdir -p ~/.config/skrivagner
cp /usr/share/doc/skrivagner/examples/config.exemple.json ~/.config/skrivagner/config.json
chmod 600 ~/.config/skrivagner/config.json
```

Compruebe la instalación, sin escribir nada:

```bash
skrivagner --version
skrivagner --diagnose
```

El paquete coloca el comando en `/usr/bin/skrivagner`, el programa en `/usr/lib/skrivagner/`, y los README, la configuración de ejemplo y la página de manual (`man skrivagner`, en cuatro idiomas) en `/usr/share/`. La desinstalación conserva sus datos: `sudo apt remove skrivagner` y `sudo apt purge skrivagner` eliminan los archivos del paquete y nunca tocan su configuración, su estado, su diario ni sus documentos; la purga nombra lo que deja.

Nivel: instalación y diagnóstico validados en contenedor en Debian 12 y 13 y en Ubuntu 22.04 y 24.04 (instalación, `--version`, `--diagnose`, la negativa a escribir sin configuración y la de escribir en una bóveda no montada, una clasificación simulada, desinstalación y purga). Un contenedor no muestra ni el montaje de una bóveda cifrada ni una ejecución con su propio Ollama y sus propios documentos.

## Instalación desde las fuentes

Árbol final (`~` es su directorio personal; adapte las rutas a su instalación):

```
~/applications/skrivagner/               el repositorio clonado
├── skrivagner.py                        el punto de entrada
├── modules/                             un archivo por responsabilidad
│   └── langues/                         los diccionarios de mensajes: en, fr, de, es
├── docs/                                las traducciones de este README y la página de manual
├── tests/                               las pruebas
├── config.exemple.json                  la configuración de ejemplo, versionada
└── venv/                                el entorno de Python, creado en el paso 2
~/.config/skrivagner/config.json         su configuración, creada en el paso 3, nunca versionada
~/.local/state/skrivagner/               el estado, el diario y los informes de sesión (ubicación por defecto)
~/Classement/Personnel/                  la bóveda del ámbito personal
~/Classement/Professionnel/              la bóveda del ámbito profesional
```

1. Clonar el repositorio:

```bash
mkdir -p ~/applications && git clone https://github.com/RonanDavalan/skrivagner.git ~/applications/skrivagner
cd ~/applications/skrivagner
```

2. Crear el entorno de Python y comprobar las pruebas (esperado: `410 passed, 6 skipped`; los 6 omitidos son los ensayos contra un Ollama que responde):

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q tests
```

3. Crear la configuración, con modo `600`. Skrivagner lee el primer archivo que encuentra entre: la opción `--config <ruta>`, la variable de entorno `SKRIVAGNER_CONFIG`, `~/.config/skrivagner/config.json` (o `$XDG_CONFIG_HOME/skrivagner/config.json`), y después `config.json` junto a `skrivagner.py`. Una opción o variable que designe un archivo ausente detiene el programa: nunca recurre a otro archivo.

```bash
mkdir -p ~/.config/skrivagner
cp config.exemple.json ~/.config/skrivagner/config.json
chmod 600 ~/.config/skrivagner/config.json
```

4. Crear las dos bóvedas y leer el tipo de su sistema de archivos:

```bash
mkdir -p ~/Classement/Personnel ~/Classement/Professionnel
findmnt -n -T ~/Classement/Personnel -o FSTYPE
```

El comando muestra por ejemplo `ext4`. Antes de cada escritura, Skrivagner comprueba que la raíz de cada bóveda está montada, porque una bóveda cerrada deja una carpeta vacía en el disco sin cifrar: compara este tipo con `systemes_fichiers_acceptes`. El ejemplo espera `fuse.gocryptfs`. Si cifra de otro modo (LUKS, eCryptfs…), abra el volumen y escriba el tipo que `findmnt` devuelve para él. En un volumen sin cifrar, esta comprobación ya no distingue un montaje ausente de uno presente: renuncia entonces a esta protección.

5. Editar `~/.config/skrivagner/config.json`, estas claves como mínimo:

| Clave | Función |
|---|---|
| `destinations.personnel.racine` y `destinations.professionnel.racine` | las dos bóvedas, aquí `~/Classement/Personnel` y `~/Classement/Professionnel` |
| `destinations.*.systemes_fichiers_acceptes` | el tipo leído en el paso 4 |
| `personnes` | los nombres de pila del hogar, que dan nombre a las carpetas del ámbito personal |
| `sources_locales[].chemin` | los directorios que se escanean |
| `suivi.fichier_date`, `suivi.journal`, `suivi.sessions` | si faltan, el estado se escribe sin cifrar en `~/.local/state/skrivagner/` (o `$XDG_STATE_HOME/skrivagner/`); para cifrarlo, añada estas tres claves dentro de la bóveda (por ejemplo `~/Classement/Personnel/logs/…`): el diario es un dato sensible |
| `ollama.roles` | para cada rol, los modelos preferidos por orden; se retiene el primero instalado |

La lista completa de claves y su efecto está en `config.exemple.json`, cuyos bloques son todos ejemplos realistas. Las contraseñas nunca entran en él.

6. Comprobar la instalación, sin escribir nada:

```bash
venv/bin/python skrivagner.py --version
venv/bin/python skrivagner.py --diagnose
```

`--version` escribe una línea y termina:

```
skrivagner 0.9.0-alpha
```

`--diagnose` escribe una línea por comprobación, `<ESTADO> <identificador> : <mensaje>`, y luego un resumen. En un directorio personal nuevo, sin configuración ni Ollama, la salida es la siguiente y el código de salida es `0`:

```
OK python : 3.13.5
OK outil_pdftotext : /usr/bin/pdftotext
OK outil_pdftoppm : /usr/bin/pdftoppm
OK outil_findmnt : /usr/bin/findmnt
OK outil_ssh : /usr/bin/ssh
NON_CONFIGURÉ configuration : ninguna configuración encontrada (la opción --config: no indicada; la variable SKRIVAGNER_CONFIG: no indicada; la ubicación XDG: ~/.config/skrivagner/config.json; la carpeta del script: ~/applications/skrivagner/config.json)
NON_VÉRIFIÉ emplacement_etat : depende de la configuración
NON_VÉRIFIÉ ollama : depende de la configuración
NON_VÉRIFIÉ modele_ocr : depende de la configuración
NON_VÉRIFIÉ modele_tri_rapide : depende de la configuración
NON_VÉRIFIÉ modele_classification : depende de la configuración
NON_VÉRIFIÉ destination_personnel : depende de la configuración
NON_VÉRIFIÉ destination_professionnel : depende de la configuración
Diagnóstico: 5 OK, 0 advertencia(s), 0 fallo(s), 1 sin configurar, 7 sin comprobar
```

Los símbolos de estado (`OK`, `AVERTISSEMENT`, `ÉCHEC`, `NON_CONFIGURÉ`, `NON_VÉRIFIÉ`) y los identificadores son los mismos en todos los idiomas, para que un script pueda compararlos. Una vez escrita la configuración, todo lo que declara y la máquina no cumple (Ollama apagado, modelo ausente, bóveda sin montar) es un `ÉCHEC` y el código de salida vale `1`. Con la configuración del paso 5 rellenada y las bóvedas montadas, la salida termina con un resumen como este:

```
Diagnóstico: 12 OK, 1 advertencia(s), 0 fallo(s), 0 sin configurar, 0 sin comprobar
```

La única advertencia es el estado y el diario sin cifrar en `~/.local/state/skrivagner/`, mientras no los traslade a una bóveda.

## Idioma de los mensajes

Skrivagner escribe sus mensajes en inglés, francés, alemán o español. El idioma se lee una vez al arrancar, en la primera de las variables `LC_ALL`, `LC_MESSAGES` y `LANG` que no esté vacía: `fr_FR.UTF-8` da francés, `de_DE.UTF-8` alemán, `es_ES.UTF-8` español, `en_US.UTF-8` inglés, y cualquier otro valor, o ninguno, inglés. Para leer la misma comprobación en otro idioma:

```bash
LC_ALL=fr_FR.UTF-8 venv/bin/python skrivagner.py --diagnose
```

Los nombres de las opciones, los símbolos de estado, los identificadores, los diarios y los archivos de plan nunca cambian con el idioma: lo que se escribe en el disco está en inglés, para que un diario escrito en un idioma se reproduzca con `--rollback` en cualquier otro. Los diccionarios de mensajes son los archivos `modules/langues/en.txt`, `fr.txt`, `de.txt` y `es.txt`.

## Uso

```bash
cd ~/applications/skrivagner
venv/bin/python skrivagner.py --dry-run     # simulación (por defecto): nada se mueve
venv/bin/python skrivagner.py --execute     # clasificación real
venv/bin/python skrivagner.py --rollback    # deshace la última sesión de clasificación
venv/bin/python skrivagner.py --inventaire  # lee lo que ya contienen las bóvedas, no se mueve nada
venv/bin/python skrivagner.py --diagnose    # comprueba la instalación, la configuración, Ollama y las bóvedas, sin escribir nada
venv/bin/python skrivagner.py --version     # escribe una línea, `skrivagner <versión>`, y termina
venv/bin/python skrivagner.py --dry-run --config ~/otra/config.json   # lee esa configuración
venv/bin/python skrivagner.py --help        # lista todas las opciones, en el idioma de la sesión
```

Empiece siempre con `--dry-run`, revise cada destino propuesto y después lance `--execute`. La primera pasada es lenta (varios modelos leen cada documento); la salida de error muestra el avance, `modelo i/n, documento j/m`. Aquí tiene un `--dry-run` sobre una carpeta de origen vacía, que necesita Ollama y los tres modelos de los roles:

```
Skrivagner 0.9.0-alpha — sesión 2026-10-29T17:33:30
  Modo               : dry-run
  Configuración      : ~/.config/skrivagner/config.json
  Bóveda personnel     : ~/Classement/Personnel — montada
  Bóveda professionnel : ~/Classement/Professionnel — montada
  Diario de sesión   : ~/.local/state/skrivagner/sessions/session_2026-10-29T17:33:30.jsonl
  Modelo ocr           : glm-ocr:latest
  Modelo tri_rapide    : gemma3:4b
  Modelo classification: granite4.2:8b-Q5_K_M
  Consenso           : 1 modelo(s) de clasificación, umbral 0.4

Origen: entrant (~/Classement/Entrant)
  (ningún archivo candidato)
  Total del origen: 0 archivo(s), 0 B

============================================================
Total del escaneo: 0 archivo(s) candidato(s), 0 B
============================================================
Extracción del texto (el texto no se muestra ni se escribe)

Clasificación (dry-run, no se mueve nada; el texto no se muestra ni se escribe)
```

Códigos de salida:

| Código | Significado |
|---|---|
| `0` | éxito |
| `1` | configuración no encontrada, no válida o con una clave ausente; al menos un origen o un documento con fallo; rollback solo parcial; consentimiento OAuth2 fallido; `--diagnose` con al menos un `ÉCHEC` |
| `2` | bóveda no comprobada como montada antes de un modo que escribe; línea de comandos no válida |
| `3` | ningún modelo instalado para un rol (`ollama list`), o Ollama no responde |
| `4` | `--execute` rechazado en esta máquina (clave `executer_sur`) |
| `5` | otra ejecución mantiene el bloqueo `skrivagner.verrou` (junto a `suivi.fichier_date`) |

Cada traslado se anota en el diario de acciones (`suivi.journal`, una línea JSON por acción, sin texto de documento) y cada sesión deja un informe en `suivi.sessions`. `--rollback --session <marca de tiempo>` deshace una sesión concreta: el documento vuelve a su lugar de origen, copia verificada por huella.

### Página de manual

La página de manual está escrita en Markdown en `docs/skrivagner.1.md`, con sus traducciones en `docs/fr-FR/`, `docs/de-DE/` y `docs/es-ES/`. Para leerla desde las fuentes:

```bash
pandoc --standalone --from markdown-smart --to man docs/es-ES/skrivagner.1.md | man -l -
```

### Máquinas remotas por ssh

Declare cada máquina en `sources_distantes` (alias `ssh`, directorios, `vide_poches_destination`). `ssh <alias> true` debe funcionar sin contraseña, y la máquina debe ofrecer `find`, `sha256sum` y `cat`. En simulación, Skrivagner lista los archivos sin copiar nada; en ejecución, los copia en la carpeta de entrada de la máquina, verifica su huella y luego los trata como archivos locales. Los archivos originales quedan intactos. Una conexión rechazada detiene la máquina afectada: no reintente en bucle.

### Buzones de correo por IMAP

Declare cada buzón en `sources_imap`. La contraseña se lee en la variable de entorno que nombra `mot_de_passe_env`, nunca en el archivo:

```bash
read -rs SKRIVAGNER_IMAP_EXEMPLE && export SKRIVAGNER_IMAP_EXEMPLE
```

Skrivagner abre las carpetas en solo lectura (`EXAMINE`) y solo lee el adjunto (`BODY.PEEK`): ningún mensaje se marca como leído, ninguna bandera se coloca.

### Cuentas de Google por OAuth2

Una cuenta de Google se lee con un token OAuth2 en lugar de la contraseña (`AUTHENTICATE XOAUTH2`). En la [consola de Google Cloud](https://console.cloud.google.com), con la cuenta que se va a leer: crear un proyecto, activar la API de Gmail, configurar la pantalla de consentimiento OAuth (tipo externo), después **publicarla** (estado «In production», porque en «Testing» la autorización caduca a los siete días), y por último crear una credencial «Aplicación de escritorio» y descargar su JSON. Guárdelo en la bóveda, con modo `600`, declare luego el origen con `"authentification": "oauth2"`, `client_fichier` y `token_fichier` (véase el ejemplo `imap-google-exemple`) y consienta una sola vez:

```bash
venv/bin/python skrivagner.py --autoriser-google imap-google-exemple
```

Abra la dirección mostrada en un navegador, acepte la advertencia «aplicación no verificada» (es su propia aplicación) y el consentimiento. El token se escribe con modo `600` en la carpeta del `token_fichier`, que rechaza un repositorio git y las rutas de `oauth2.chemins_interdits`; se renueva solo y no aparece ni en el diario ni en pantalla. Si Google lo revoca (acceso retirado, contraseña de la cuenta cambiada, seis meses sin escaneo), Skrivagner se detiene con un mensaje explícito: repita el comando.

## Soberanía

- Las llamadas a Ollama son peticiones HTTP a `ollama.url` (por defecto `http://localhost:11434`); ningún documento ni nombre de archivo va a otra parte.
- Los únicos servicios externos que el código puede alcanzar son los que usted declara: sus máquinas por `ssh`, sus buzones IMAP y, si activa OAuth2, los puntos de autorización de Google.
- Ningún secreto se guarda en `config.json`: contraseñas en variable de entorno, tokens en archivos `600` fuera de todo repositorio.

## Límites

- Solo Linux. La comprobación de montaje se apoya en `findmnt`.
- La clasificación vale lo que valen sus modelos: en la instancia de referencia, un primer ensayo con 15 documentos reales clasificó 2, apartó 3 como no administrativos y dejó 10 en `À_VÉRIFIER/`, por prudencia. Mida antes de confiar: la medición del ámbito está en `_outils/mesurer_domaines.py`.
- Skrivagner no monta, no cifra ni sincroniza ninguna bóveda, y no borra ningún documento: el espacio en disco y las copias de seguridad corren por su cuenta.
- Las categorías, los remitentes conocidos y la plantilla de nombres de `config.exemple.json` reflejan la vida administrativa francesa (caja de subsidios familiares, hacienda, seguros); adáptelas a su país.
- Los pasos en la consola de Google dependen de la interfaz de Google, que cambia: las nociones siguen siendo las de su documentación OAuth2.
- El proyecto es joven: versión 0.9.0-alpha, sin integración continua.

## Contribuir, informar de una vulnerabilidad

Véase [CONTRIBUTING.md](../../CONTRIBUTING.md). Una vulnerabilidad se comunica en privado según [SECURITY.md](../../SECURITY.md), nunca en una incidencia pública.

## Créditos

Skrivagner es fruto de una colaboración entre una persona y modelos de lenguaje, con los roles escritos tal como se desempeñaron. La lista completa está en [CONTRIBUTORS.md](../../CONTRIBUTORS.md).

*   **Ronan Davalan**: arquitecto y árbitro; visión, decisiones, alcance, validación. Único autor de git.
*   **Claude Code (Anthropic)**: ingeniero de realización; código Python y pruebas, y los documentos públicos (este README y sus traducciones, la página de manual, `CONTRIBUTING.md`, `SECURITY.md`).
*   **Gemini (Google)**: asesor de diseño; propuso el nombre original «Le Greffier».
*   **Copilot (Microsoft)**: tradujo ese nombre al bretón, de ahí «Skrivagner».
