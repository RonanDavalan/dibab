# Dibab

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://dibab.davalan.fr/images/logo-sombre.svg">
    <img src="https://dibab.davalan.fr/images/logo-clair.svg" alt="Dibab 标志" width="320">
  </picture>
</p>

<p align="center">
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-AGPL_v3-blue.svg" alt="许可证：AGPL v3"></a>
  <img src="https://img.shields.io/badge/Version-0.9.0--alpha-yellow.svg" alt="版本：0.9.0-alpha">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Linux-Debian_%C2%B7_Ubuntu-blue.svg" alt="Debian 和 Ubuntu">
</p>

[English](../../README.md) | [Français](../fr-FR/README.md) | [Deutsch](../de-DE/README.md) | [Español](../es-ES/README.md) | **中文**

Dibab（布列塔尼语意为“选择”）收集、分析并归档一个家庭的个人行政文件（发票、信件、合同、公共机构的通知），放入规范化的目录树中，并把它所做的一切记入日志。它以自主模式运行：任何文件及其文本都不离开本地网络，不使用远程模型，也不使用云。与外部的连接只有您声明的那些：Dibab 读取的 IMAP 邮箱，以及当该邮箱是 Google 账户时 Google 的 OAuth2 授权。语言模型是您自己机器上 [Ollama](https://ollama.com/) 提供的模型。

许可证：[GNU Affero 通用公共许可证第 3 版](../../LICENSE)。

## Dibab 做什么，不做什么

它会：

- 扫描本地目录、通过 `ssh` 访问的远程机器（复制件经指纹校验，原文件保持原样）以及只读方式访问的 IMAP 邮箱（附件放入“投放文件夹”，邮箱不被修改）；
- 提取文本（优先使用 PDF 的文本层，否则由视觉模型识读），把行政文件与其他文件分开，再由多个模型达成共识后按类别和领域（个人或业务）归档；
- 重命名每份文件并移入相应领域的保险库，记录带时间戳的日志，并可以撤销（`--rollback`）。

它不会：

- 移动它没有把握的文件：有疑问就放入 `待核实/` 文件夹，绝不冒险归档；
- 删除文件：它只移动和复制，不抹除（只清理自己的旧日志，见 PDF 手册第 8 章“清单与轮转”）；
- 修改邮箱或远程机器；
- 在后台运行：由您手动启动，默认模式是模拟（`--dry-run`）；
- 挂载、加密或同步保险库：这些由您负责（见“局限”）。

## 为家庭打造的工具

Dibab 为家庭的行政事务而设计，由家庭自己使用。只有在当事人明示或默示同意的情况下，一台机器、一个目录或一个邮件账户才纳入范围；有疑问时就不纳入。软件无法保证做到这种尊重：实例的管理员对此作出承诺。运行日志记录每份文件的主题、发件机构、类别、人员和日期，这些已经透露很多信息（一封医疗机构的来信就足够）：它应当放在保险库内，而不是旁边：把三个 `suivi.*` 键指向保险库内部即可，否则它会以明文写在 `~/.local/state/dibab/` 下。

## 环境要求

- Linux，Python 3.10 或更高版本（测试在 3.12 和 3.13 上通过）；代码只使用标准库；
- `findmnt`（软件包 `util-linux`）和 `git`；
- `pdftotext` 和 `pdftoppm`（软件包 `poppler-utils`）；
- 已安装并正在运行的 [Ollama](https://ollama.com/)，每个角色至少一个模型；
- 访问远程机器需要 `ssh`，并使用无需密码即可打开会话的密钥；
- 每个领域一个目标目录，最好位于加密卷上。

在 Debian 上：

```bash
sudo apt install python3 python3-venv git util-linux poppler-utils openssh-client
```

按角色划分的模型（`ocr` 识读扫描页面，`tri_rapide` 剔除非行政文件，`classification` 进行归档）：

```bash
ollama pull glm-ocr
ollama pull mistral-nemo:12b-instruct-2407-q6_K
ollama pull gemma4
ollama pull gemma3:4b
ollama pull qwen2.5
ollama pull granite4.2:8b-Q5_K_M
```

这些是参考实例使用的模型；其他模型同样可以，只需在 `ollama.roles` 中写明（见下文）。`classification` 角色的模型进行表决：只有当它们的一致度达到 `ollama.seuil_confiance` 时，文件才会归档。Ollama 不是 Dibab 的一部分，Dibab 也从不安装它。

## 用 Debian 软件包安装

在 Debian 12 和 13 以及 Ubuntu 22.04 和 24.04 上，一个文件即可安装程序及其依赖（`python3`、`poppler-utils`、`util-linux`、`openssh-client`）。它不包含 Ollama、模型和配置。从 [dibab.davalan.fr](https://dibab.davalan.fr/) 的下载页面下载 `dibab_*_all.deb`，然后在该文件所在文件夹中执行：

```bash
sudo apt install ./dibab_*_all.deb
```

以当前会话的语言写入配置，然后按下文从源代码安装的第 4 步和第 5 步操作（每个领域的保险库、配置中的键）：

```bash
dibab --initialiser
```

`--initialiser` 以当前会话的语言写入配置：核查文件夹、其前缀和重复文件夹采用该语言的名称。它在权限为 `700` 的文件夹中以 `600` 权限创建文件，从不改写已经存在的文件；之后用另一种语言运行也不会重命名它们。

检查安装，不写入任何内容：

```bash
dibab --version
dibab --diagnose
```

软件包把命令放在 `/usr/bin/dibab`，程序放在 `/usr/lib/dibab/`，README、示例配置和手册页（`man dibab`，五种语言）放在 `/usr/share/` 下。卸载会保留您的数据：`sudo apt remove dibab` 和 `sudo apt purge dibab` 只删除软件包的文件，从不触碰您的配置、状态、日志和文件；清除时会列出它保留的内容。

验证程度：安装和诊断已在容器中于 Debian 12 和 13 以及 Ubuntu 22.04 和 24.04 上验证（安装、`--version`、`--diagnose`、无配置时拒绝写入、保险库未挂载时拒绝写入、一次模拟归档、卸载和清除）。容器无法验证加密保险库的挂载，也无法验证使用您自己的 Ollama 和文件的运行。

## 从源代码安装

最终目录树（`~` 是您的主目录；请按您的安装调整路径）：

```
~/applications/dibab/               克隆的仓库
├── dibab.py                        入口文件
├── modules/                             每项职责一个文件
│   └── langues/                         消息词典： en, fr, de, es, zh
├── docs/                                本 README 和手册页的译文
├── tests/                               测试
├── config.exemple.json                  示例配置，纳入版本管理
└── venv/                                Python 环境，在第 2 步创建
~/.config/dibab/config.json         您的配置，在第 3 步创建，从不纳入版本管理
~/.local/state/dibab/               状态、日志和运行报告（默认位置）
~/Classement/Personnel/                  个人领域的保险库
~/Classement/Professionnel/              业务领域的保险库
```

1. 克隆仓库：

```bash
mkdir -p ~/applications && git clone https://github.com/RonanDavalan/dibab.git ~/applications/dibab
cd ~/applications/dibab
```

2. 创建 Python 环境并运行测试（预期结果：`581 passed, 9 skipped`；跳过的 9 项是针对正在运行的 Ollama 的试验）：

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q tests
```

3. 以当前会话的语言写入配置。Dibab 读取以下位置中找到的第一个文件：`--config <path>` 选项、`DIBAB_CONFIG` 环境变量、`~/.config/dibab/config.json`（或 `$XDG_CONFIG_HOME/dibab/config.json`），最后是 `dibab.py` 旁的 `config.json`。如果选项或变量指向不存在的文件，程序会停止：绝不退而使用另一个文件。

```bash
venv/bin/python dibab.py --initialiser
```

`--initialiser` 以当前会话的语言写入配置：核查文件夹、其前缀和重复文件夹采用该语言的名称。它在权限为 `700` 的文件夹中以 `600` 权限创建文件，从不改写已经存在的文件；之后用另一种语言运行也不会重命名它们。

4. 为每个领域创建保险库，并读取其文件系统类型：

```bash
mkdir -p ~/Classement/Personnel ~/Classement/Professionnel
findmnt -n -T ~/Classement/Personnel -o FSTYPE
```

命令会输出例如 `ext4`。每次写入之前，Dibab 都会确认每个保险库的根目录已经挂载，因为关闭的保险库会在明文磁盘上留下一个空文件夹：它把该类型与 `systemes_fichiers_acceptes` 进行比较。示例中期望的是 `fuse.gocryptfs`。如果您使用其他加密方式（LUKS、eCryptfs 等），请打开卷并写入 `findmnt` 返回的类型。在未加密的卷上，这项检查无法区分未挂载与已挂载：您将因此失去这层保护。

5. 编辑 `~/.config/dibab/config.json`，至少设置以下键：

| 键 | 作用 |
|---|---|
| `destinations.personnel.racine` 和 `destinations.professionnel.racine` | 各领域的保险库，此处为 `~/Classement/Personnel` 和 `~/Classement/Professionnel` |
| `destinations.*.systemes_fichiers_acceptes` | 第 4 步读到的类型 |
| `personnes` | 家庭成员的名字，用于命名个人领域的文件夹 |
| `sources_locales[].chemin` | 要扫描的目录 |
| `suivi.fichier_date`、`suivi.journal`、`suivi.sessions` | 缺省时，状态以明文写在 `~/.local/state/dibab/`（或 `$XDG_STATE_HOME/dibab/`）下；要加密，请把这三个键指向保险库内部（例如 `~/Classement/Personnel/logs/...`）：日志属于敏感数据 |
| `ollama.roles` | 每个角色按优先顺序列出模型；保留第一个已安装的模型 |

完整的键列表及其作用：请阅读 `config.exemple.json`，其中每个区块都是一个贴近实际的示例。密码从不写入其中。

6. 检查安装，不写入任何内容：

```bash
venv/bin/python dibab.py --version
venv/bin/python dibab.py --diagnose
```

`--version` 输出一行后停止：

```
dibab 0.9.1-alpha
```

`--diagnose` 每项检查输出一行 `<STATE> <identifier> : <message>`，最后给出汇总。在没有配置也没有 Ollama 的全新主目录中，输出如下，退出码为 `0`：

```
OK python : 3.13.5
OK outil_pdftotext : /usr/bin/pdftotext
OK outil_pdftoppm : /usr/bin/pdftoppm
OK outil_findmnt : /usr/bin/findmnt
OK outil_ssh : /usr/bin/ssh
NON_CONFIGURÉ configuration : 找不到任何配置（--config 选项：未提供; DIBAB_CONFIG 环境变量：未提供; XDG 位置：~/.config/dibab/config.json; 脚本所在文件夹：~/applications/dibab/config.json）
NON_VÉRIFIÉ emplacement_etat : 取决于配置
NON_VÉRIFIÉ ollama : 取决于配置
NON_VÉRIFIÉ modele_ocr : 取决于配置
NON_VÉRIFIÉ modele_tri_rapide : 取决于配置
NON_VÉRIFIÉ modele_classification : 取决于配置
NON_VÉRIFIÉ modele_tri_decision : 取决于配置
NON_VÉRIFIÉ destination_personnel : 取决于配置
NON_VÉRIFIÉ destination_professionnel : 取决于配置
诊断结果：5 项正常，0 项警告，0 项失败，1 项未配置，8 项未检查
```

本例中的路径对应从源代码安装的情况。若用软件包安装，脚本所在文件夹是 `/usr/lib/dibab/`，`~` 是您自己的主目录。

状态标记（`OK`、`AVERTISSEMENT`、`ÉCHEC`、`NON_CONFIGURÉ`、`NON_VÉRIFIÉ`）和标识符在所有语言中都相同，便于脚本比较。一旦写入配置，凡是配置声明了而机器上不具备的项目（Ollama 未运行、缺少模型、保险库未挂载）都是 `ÉCHEC`，退出码为 `1`。填好第 5 步的配置并挂载各保险库后，输出末尾是类似下面的汇总：

```
诊断结果：12 项正常，1 项警告，0 项失败，1 项未配置，0 项未检查
```

在此处使用的配置下，诊断给出一条警告：状态和日志以明文保存在 `~/.local/state/dibab/` 下，直到您把它们移入保险库。只要您没有声明决策分拣（`ollama.roles.tri_decision`）且 Ollama 有响应，它就保持 `NON_CONFIGURÉ`：分拣改用 `tri_rapide`。当 Ollama 没有响应时，它与其他模型一样是 `NON_VÉRIFIÉ`，该次运行的三项失败是 Ollama 和两个保险库文件夹。

## 消息语言

Dibab 的消息有英文、法文、德文、西班牙文和简体中文。语言在启动时读取一次，取 `LC_ALL`、`LC_MESSAGES` 和 `LANG` 中第一个非空的变量：`fr_FR.UTF-8` 为法文，`de_DE.UTF-8` 为德文，`es_ES.UTF-8` 为西班牙文，`zh_CN.UTF-8` 为简体中文，`en_US.UTF-8` 为英文，其他值或未设置则为英文。所有 `zh_*` 区域设置都使用简体中文。要用另一种语言阅读同一项检查：

```bash
LC_ALL=zh_CN.UTF-8 venv/bin/python dibab.py --diagnose
```

选项名称、状态标记、标识符、日志和计划文件从不随语言变化：日志和计划文件的键（`evenement`、`horodatage` 等）以及表示事件或类别的值（`session_demarree`、`administratif` 等）是固定的技术标识符，用法语书写，因此用一种语言写下的日志可以在任何语言下用 `--rollback` 回放。消息词典是文件 `modules/langues/en.txt`、`fr.txt`、`de.txt`、`es.txt` 和 `zh.txt`。

核查文件夹、其前缀和重复文件夹的名称在初始化时按会话语言写入；它们由 `sous_repertoire_a_verifier`、`nommage.prefixe_a_verifier` 和 `destination.repertoire_doublon` 设定，之后用另一种语言运行也不会重命名它们。

## 使用方法

```bash
cd ~/applications/dibab
venv/bin/python dibab.py --dry-run     # 模拟（默认）：不移动任何内容
venv/bin/python dibab.py --execute     # 实际归档
venv/bin/python dibab.py --rollback    # 撤销最近一次归档
venv/bin/python dibab.py --inventaire  # 读取各保险库中已有的内容，不移动任何文件
venv/bin/python dibab.py --diagnose    # 检查安装、配置、Ollama 和各领域的保险库，不写入任何内容
venv/bin/python dibab.py --version     # 输出一行 `dibab <version>` 后停止
venv/bin/python dibab.py --dry-run --config ~/other/config.json   # 读取该配置
venv/bin/python dibab.py --help        # 以会话语言列出所有选项
```

始终先用 `--dry-run`，逐一阅读建议的目标位置，然后再运行 `--execute`。第一次处理较慢（每份文件由多个模型阅读）；错误输出显示进度，即模型序号与文件序号。下面是对一个空的来源文件夹执行 `--dry-run` 的结果，需要 Ollama 和三个角色的模型：

```
Dibab 0.9.1-alpha — 本次运行 2026-11-26T00:07:10
  模式：dry-run
  配置：~/.config/dibab/config.json
  保险库 personnel     ：~/Classement/Personnel — 已挂载
  保险库 professionnel ：~/Classement/Professionnel — 已挂载
  运行日志：~/.local/state/dibab/sessions/session_2026-11-26T00:07:10.jsonl
  模型 ocr           ：glm-ocr:latest
  模型 tri_rapide    ：gemma3:4b
  模型 classification：granite4.2:8b-Q5_K_M
  共识：1 个归类模型，阈值 0.4

来源：entrant（~/Classement/Entrant）
  （没有候选文件）
  该来源合计：0 个文件，0 B

============================================================
扫描合计：0 个候选文件，0 B
============================================================
文本提取（文本既不显示也不写入）

归类（模拟，不移动任何文件；文本既不显示也不写入）
```

退出码：

| 退出码 | 含义 |
|---|---|
| `0` | 成功 |
| `1` | 找不到配置、配置无效或缺少键；至少一个来源或文件失败；撤销只部分完成；OAuth2 授权失败；`--diagnose` 至少有一项 `ÉCHEC` |
| `2` | 在会写入的模式之前无法确认保险库已挂载；命令行无效 |
| `3` | 某个角色没有已安装的模型（`ollama list`），或 Ollama 没有响应 |
| `4` | 本机拒绝执行 `--execute`（键 `executer_sur`） |
| `5` | 另一次运行持有锁 `dibab.verrou`（位于 `suivi.fichier_date` 旁） |

每次移动都写入操作日志（`suivi.journal`，每个操作一行 JSON，不含文件文本），每次运行在 `suivi.sessions` 中留下一份报告。`--rollback --session <timestamp>` 撤销指定的运行：文件回到原来的位置，复制件经指纹校验。

指纹已经归档过的文件会复制到保险库根目录下的 `重复/` 文件夹，经校验后从来源移除，与归档文件一样处理；清空该文件夹由您决定。因另一次运行持有锁而被拒绝的运行，会在其运行日志中留下一行 `session_refusee`。

### 手册页

手册页以 Markdown 编写于 `docs/dibab.1.md`，译文位于 `docs/fr-FR/`、`docs/de-DE/`、`docs/es-ES/` 和 `docs/zh-CN/`。从源代码阅读：

```bash
pandoc --standalone --from markdown-smart --to man docs/zh-CN/dibab.1.md | man -l -
```

### 通过 ssh 访问远程机器

在 `sources_distantes` 中声明每台机器（`ssh` 别名、目录、`vide_poches_destination`）。`ssh <alias> true` 必须无需密码即可成功，且机器须提供 `find`、`sha256sum` 和 `cat`。模拟模式下，Dibab 只列出文件而不复制；实际执行时，它把文件复制到该机器的投放文件夹，校验指纹，然后按本地文件处理。原文件保持原样。连接被拒绝时，相应机器的处理停止：请勿反复重试。

### 通过 IMAP 访问邮箱

在 `sources_imap` 中声明每个邮箱。密码从 `mot_de_passe_env` 指定的环境变量读取，绝不从文件读取：

```bash
read -rs DIBAB_IMAP_EXEMPLE && export DIBAB_IMAP_EXEMPLE
```

Dibab 以只读方式打开文件夹（`EXAMINE`），只读取附件（`BODY.PEEK`）：不会把任何邮件标为已读，也不设置任何标志。

### 通过 OAuth2 访问 Google 账户

Google 账户使用 OAuth2 令牌代替密码读取（`AUTHENTICATE XOAUTH2`）。用要读取的账户登录 [Google Cloud 控制台](https://console.cloud.google.com)：创建项目，启用 Gmail API，配置 OAuth 同意屏幕（外部类型），然后**发布**它（状态为“In production”，因为在“Testing”状态下授权七天后过期），最后创建一个“桌面应用”凭据并下载其 JSON。以 `600` 权限保存在保险库中，然后用 `"authentification": "oauth2"`、`client_fichier` 和 `token_fichier` 声明该来源（参见示例 `imap-google-exemple`），并授权一次：

```bash
venv/bin/python dibab.py --autoriser-google imap-google-exemple
```

在浏览器中打开输出的地址，接受“未经验证的应用”警告（这是您自己的应用）并同意授权。令牌以 `600` 权限写入 `token_fichier` 所在文件夹，该位置不允许是 git 仓库或 `oauth2.chemins_interdits` 中的路径；令牌会自动续期，从不出现在日志或屏幕上。如果 Google 撤销了它（取消访问、修改账户密码、六个月没有扫描），Dibab 会给出明确消息并停止：请重新运行该命令。

## 自主性

- 对 Ollama 的调用是发往 `ollama.url`（默认 `http://localhost:11434`）的 HTTP 请求；文件和文件名不会发往任何其他地方。
- 代码能访问的外部服务只有您声明的那些：通过 `ssh` 的机器、IMAP 邮箱，以及启用 OAuth2 时 Google 的授权接口。
- `config.json` 中不保存任何机密：密码放在环境变量中，令牌放在任何仓库之外的 `600` 权限文件中。

## 局限

- 仅支持 Linux。挂载检查依赖 `findmnt`。
- 归档质量取决于您的模型：在参考实例上，对 15 份真实文件的首次试验归档了 2 份，将 3 份判为非行政文件搁置，另有 10 份出于谨慎放入了 `待核实/`。信任之前请先测量：领域判定的测量工具在 `_outils/mesurer_domaines.py`。
- Dibab 不挂载、不加密、不同步任何保险库，也不抹除任何文件：磁盘空间和备份由您负责。
- `config.exemple.json` 中的类别和已知发件机构是通用的，请按您所在国家调整。
- Google 控制台中的步骤取决于 Google 的界面，界面会变化：概念仍以其 OAuth2 文档为准。
- 项目尚年轻：版本 0.9.0-alpha，没有持续集成。

## 参与贡献与报告漏洞

参见 [CONTRIBUTING.md](../../CONTRIBUTING.md)。漏洞请按 [SECURITY.md](../../SECURITY.md) 私下报告，切勿在公开议题中提交。

## 致谢

Dibab 是一个人与多个语言模型协作的成果，角色按实际承担的情况记录。完整名单见 [CONTRIBUTORS.md](../../CONTRIBUTORS.md)。

*   **Ronan Davalan**：架构师与裁决者；愿景、决策、范围、验收。唯一的 git 作者。
*   **Claude Code（Anthropic）**：实现工程师；Python 代码与测试、公开文档（本 README 及其译文、手册页、`CONTRIBUTING.md`、`SECURITY.md`），以及标志和网站（平面设计、版式与文字）。
*   **Gemini（Google）**：设计顾问；提出了最初的名称“Le Greffier”，并与 Ronan Davalan 讨论了 Dibab 这个名称；标志研究。
*   **Muse Spark 1.3（Meta）**：名称构思；提出了“dibab”这一方向（布列塔尼语意为“选择”），由此得名 Dibab；标志研究。
*   **DeepSeek V4.1 Flash（DeepSeek）**：测试与评审；探索性测试的报告促成了多项修复，核查了改名和网站译文，在文档和示例中使用通用名称，起草发行说明和发布配图，早期图标研究。
*   **GLM-5.3-Flash（Z.ai）**：早期图标研究。
