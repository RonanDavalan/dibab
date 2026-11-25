% DIBAB(1) dibab | Órdenes de usuario
% Ronan Davalan
% 2026-10-29

# NOMBRE

dibab - recopila, analiza y clasifica los documentos administrativos personales de un hogar, sin que ningún dato salga de la red local

# SINOPSIS

**dibab** [**\--config** *RUTA*] [**\--dry-run** | **\--execute** | **\--inventaire**]

**dibab** **\--dry-run** **\--verdicts-simules** *ARCHIVO*

**dibab** [**\--config** *RUTA*] **\--rollback** [**\--session** *SESIÓN*]

**dibab** [**\--config** *RUTA*] **\--autoriser-google** *ID*

**dibab** [**\--config** *RUTA*] **\--diagnose**

**dibab** {**\--version** | **\--help**}

# DESCRIPCIÓN

**dibab** escanea directorios locales, máquinas remotas por **ssh**(1) y buzones de correo por IMAP en solo lectura. Extrae el
texto de cada documento, aparta lo que no es administrativo y clasifica el resto por categoría y por ámbito, personal o profesional,
por consenso de varios modelos de lenguaje. Cada documento se renombra y se mueve a la bóveda de su ámbito, con un diario que
**\--rollback** puede deshacer. Nunca destruye un documento: el original se retira solo tras una copia verificada; nunca modifica un
buzón ni una máquina remota, y no mueve nada de lo que no esté seguro: la duda lleva a una carpeta llamada *POR_VERIFICAR*, se ajusta con `sous_repertoire_a_verifier`. Un documento cuya huella ya está archivada se copia, tras comprobarlo, en la carpeta nombrada por `destination.repertoire_doublon`, `duplicado/`.

Los modelos de lenguaje son los de Ollama, que se ejecuta en la misma máquina. Ollama y sus modelos se instalan aparte, por el usuario,
desde el sitio de Ollama: Dibab no contiene ni lo uno ni lo otro. Liste los modelos con **ollama list** y escríbalos, rol por rol,
en la clave **ollama.roles** de la configuración. Solo se alcanzan las bóvedas de destino, las máquinas y los buzones que la
configuración nombra.

El modo por defecto es la simulación. Lea siempre el resultado de **\--dry-run** antes de lanzar **\--execute**.

# OPCIONES

**\--dry-run**
:   Simulación, modo por defecto: escanea, extrae y clasifica, y muestra cada destino que elegiría. No se mueve nada.

**\--execute**
:   Modo real: cada documento se copia, se verifica por huella (SHA256) y luego se retira de su origen. Rechazado en una máquina que la
    clave **executer_sur** de la configuración no enumere.

**\--inventaire**
:   Lee lo que ya contienen las bóvedas y escribe un plan de migración para cada una. No se mueve nada.

**\--rollback**
:   Deshace la última sesión de clasificación, o la que nombra **\--session**. El documento vuelve a su lugar de origen, copia verificada
    por huella; una acción que no se puede deshacer deja todo en su sitio para ella.

**\--session** *SESIÓN*
:   Identificador de la sesión que se deshace, con **\--rollback**.

**\--autoriser-google** *ID*
:   Consentimiento OAuth2 del origen IMAP de Google llamado *ID* en la configuración. Muestra una dirección que se abre en un
    navegador y luego escribe el archivo de token del origen.

**\--diagnose**
:   Comprueba la instalación, la configuración, Ollama y las bóvedas, una línea por comprobación, y no escribe nada.

**\--verdicts-simules** *ARCHIVO*
:   Solo con **\--dry-run**: un archivo JSON que asocia un nombre de archivo a un veredicto, cuyo enrutado se muestra.

**\--config** *RUTA*
:   Archivo de configuración que se lee (véase **ARCHIVOS**).

**\--version**
:   Escribe una línea, **dibab** *versión*, y termina.

**\--help**, **-h**
:   Lista las opciones, en el idioma de la sesión.

# IDIOMA

Los mensajes se escriben en inglés, francés, alemán o español. El idioma se lee una vez al arrancar, en la primera de las variables
**LC_ALL**, **LC_MESSAGES** y **LANG** que no esté vacía: lo que precede al primer **\_**, **.** o **@** da **en**, **fr**, **de** o **es**;
cualquier otro valor, **C**, **POSIX** o ninguna variable da inglés. Los nombres de las opciones, los símbolos de estado de
**\--diagnose** (**OK**, **AVERTISSEMENT**, **ÉCHEC**, **NON_CONFIGURÉ**, **NON_VÉRIFIÉ**), los identificadores de las comprobaciones y la
línea de **\--version** nunca cambian. Las claves y los textos libres que se escriben en el disco (diarios, planes, informes) están en
inglés, sea cual sea el idioma de la sesión; los símbolos de acción (**classe**, **a_verifier**, **doublon**) y los nombres de ámbito
nunca cambian.

# INSTALACIÓN

En Debian 12 y 13 y en Ubuntu 22.04 y 24.04, el paquete Debian instala el programa, sus dependencias, las cuatro páginas de manual y la configuración de ejemplo *config.exemple.json* en */usr/share/doc/dibab/examples/*:

    sudo apt install ./dibab_*_all.deb

**sudo apt remove dibab** y **sudo apt purge dibab** eliminan los archivos del paquete y nunca tocan la configuración, el estado, el diario ni los documentos; la purga nombra lo que deja. Nivel: instalación y diagnóstico validados en contenedor en estas cuatro versiones; un contenedor no muestra ni el montaje de una bóveda cifrada ni una ejecución con su propio Ollama.

# ARCHIVOS

La configuración es el primer archivo existente de la lista siguiente, por este orden, y es el único que se lee:

1.  el archivo que nombra **\--config**;
2.  el archivo que nombra la variable **DIBAB_CONFIG**, cuando no está vacía;
3.  *$XDG_CONFIG_HOME/dibab/config.json*, o *~/.config/dibab/config.json* cuando **XDG_CONFIG_HOME** está vacía o sin definir;
4.  *config.json* en la carpeta de *dibab.py*.

Una opción o una variable que designe un archivo ausente detiene el programa con el código 1: nunca recurre a otro archivo.
*config.exemple.json* es el ejemplo, en la carpeta del programa; cópielo a una de estas ubicaciones, con modo 600.

Cuando la configuración no da las claves de **suivi**, el estado se escribe en *$XDG_STATE_HOME/dibab/*, o en
*~/.local/state/dibab/*: *dernier_scan.json*, *journal.jsonl* (el diario de acciones), *sessions/* (un diario y un informe por
sesión) y *dibab.log*. *rapatries.json*, *imap_deposes.json* y el bloqueo *dibab.verrou* están junto a *dernier_scan.json*.
Las carpetas se crean con modo 700 y los archivos con modo 600. El estado queda entonces sin cifrar en el disco: para guardarlo en una
bóveda, indique las claves **suivi.fichier_date**, **suivi.journal** y **suivi.sessions**.

Los diccionarios de mensajes son *modules/langues/en.txt*, *fr.txt*, *de.txt* y *es.txt*, en la carpeta del programa.

# ENTORNO

**DIBAB_CONFIG**
:   Ruta del archivo de configuración.

**XDG_CONFIG_HOME**, **XDG_STATE_HOME**
:   Carpetas base de la configuración y del estado por defecto.

**LC_ALL**, **LC_MESSAGES**, **LANG**
:   Idioma de los mensajes (véase **IDIOMA**).

La contraseña de un buzón IMAP se lee en la variable que nombra la clave **mot_de_passe_env** de su origen, nunca en el archivo de
configuración.

# ESTADO DE SALIDA

**0**
:   Éxito.

**1**
:   Configuración no encontrada, no válida o con una clave ausente; al menos un origen o un documento con fallo; rollback solo parcial;
    consentimiento OAuth2 fallido; **\--diagnose** con al menos un **ÉCHEC**.

**2**
:   Una bóveda no comprobada como montada, antes de un modo que escribe; línea de comandos no válida.

**3**
:   Ningún modelo instalado para un rol, u Ollama no responde.

**4**
:   **\--execute** rechazado en esta máquina (clave **executer_sur**).

**5**
:   Otra ejecución mantiene el bloqueo *dibab.verrou*.

# EJEMPLOS

Comprobar la instalación, luego simular, luego clasificar de verdad:

    dibab --diagnose
    dibab --dry-run
    dibab --execute

Leer la misma comprobación en inglés y deshacer la última sesión:

    LC_ALL=en_US.UTF-8 dibab --diagnose
    dibab --rollback

# VÉASE TAMBIÉN

**ollama**(1), **ssh**(1), **findmnt**(8), **pdftotext**(1), **pdftoppm**(1)

El README del proyecto describe la instalación desde el paquete Debian y desde las fuentes, la configuración, los orígenes por **ssh**, IMAP y OAuth2 para
Google, y los límites.

# LICENCIA

GNU Affero General Public License versión 3.
