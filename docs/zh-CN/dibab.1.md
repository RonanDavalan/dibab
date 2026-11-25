% DIBAB(1) dibab | 用户命令
% Ronan Davalan
% 2026-10-29

# 名称

dibab - 收集、分析并归档家庭的个人行政文件，且任何文件都不离开本地网络

# 概要

**dibab** [**\--config** *PATH*] [**\--dry-run** | **\--execute** | **\--inventaire**]

**dibab** **\--dry-run** **\--verdicts-simules** *FILE*

**dibab** [**\--config** *PATH*] **\--rollback** [**\--session** *SESSION*]

**dibab** [**\--config** *PATH*] **\--autoriser-google** *ID*

**dibab** [**\--config** *PATH*] **\--diagnose**

**dibab** {**\--version** | **\--help**}

# 描述

**dibab** 扫描本地目录、通过 **ssh**(1) 访问的远程机器以及只读方式访问的 IMAP 邮箱。它提取每份文件的文本，剔除非行政文件，
然后由多个语言模型达成共识，按类别和领域（个人或业务）归档其余文件。每份文件都会重命名并移入相应领域的保险库，同时记录可由
**\--rollback** 撤销的日志。它从不销毁文件：只有在复制件通过校验后才移除原件；从不修改邮箱或远程机器；没有把握的文件一概不移动：
有疑问就放入名为 *待核实* 的文件夹，该名称由 `sous_repertoire_a_verifier` 设定。指纹已经归档过的文件，经校验后复制到
`destination.repertoire_doublon` 指定的文件夹 `重复/`。

语言模型由运行在同一台机器上的 Ollama 提供。Ollama 及其模型由用户从 Ollama 网站另行安装：Dibab 两者都不包含。用
**ollama list** 列出模型，然后按角色写入配置的 **ollama.roles** 键。只会访问配置中指定的各领域目标保险库、机器和邮箱。

默认模式是模拟。运行 **\--execute** 之前，务必先阅读 **\--dry-run** 的结果。

# 选项

**\--dry-run**
:   模拟（默认模式）：扫描、提取并归类，输出它将选择的每个目标位置。不移动任何文件。

**\--execute**
:   实际模式：每份文件先复制，经指纹（SHA256）校验后从来源移除。如果配置的 **executer_sur** 键未列出本机，则拒绝执行。

**\--inventaire**
:   读取每个保险库中已有的内容，并为每个保险库写出迁移计划。不移动任何文件。

**\--rollback**
:   撤销最近一次归档，或由 **\--session** 指定的那一次。文件回到原来的位置，复制件经指纹校验；无法撤销的操作会让相关内容保持原样。

**\--session** *SESSION*
:   要撤销的运行的标识符，与 **\--rollback** 一起使用。

**\--autoriser-google** *ID*
:   为配置中名为 *ID* 的 Google IMAP 来源进行 OAuth2 授权。输出需在浏览器中打开的地址，然后写入该来源的令牌文件。

**\--diagnose**
:   检查安装、配置、Ollama 和各领域的保险库，每项检查一行，不写入任何内容。

**\--verdicts-simules** *FILE*
:   仅与 **\--dry-run** 一起使用：将文件名对应到判定结果的 JSON 文件，并输出其归档路径。提取和模型归类仍会运行；该文件只是补充所给判定的归档路径。

**\--config** *PATH*
:   要读取的配置文件（见 **文件**）。

**\--version**
:   输出一行 **dibab** *version* 后停止。

**\--help**, **-h**
:   以当前会话的语言列出选项。

# 语言

消息有英文、法文、德文、西班牙文和简体中文。语言在启动时读取一次，取 **LC_ALL**、**LC_MESSAGES** 和 **LANG** 中第一个非空的变量：
第一个 **\_**、**.** 或 **@** 之前的部分给出 **en**、**fr**、**de**、**es** 或 **zh**；其他值、**C**、**POSIX** 或未设置变量时使用英文。
选项名称、**\--diagnose** 的状态标记（**OK**、**AVERTISSEMENT**、**ÉCHEC**、**NON_CONFIGURÉ**、**NON_VÉRIFIÉ**）、检查项标识符和
**\--version** 输出行从不变化。写入磁盘的键（日志、计划、报告）是用法语书写的固定标识符（**evenement**、**horodatage**），
其中的自由文本一律为英文，与会话语言无关；操作标记（**classe**、**a_verifier**、**doublon**）和领域名称从不变化。

# 安装

在 Debian 12 和 13 以及 Ubuntu 22.04 和 24.04 上，Debian 软件包会安装程序、依赖、五种语言的手册页，以及位于
*/usr/share/doc/dibab/examples/* 的示例配置 *config.exemple.json*：

    sudo apt install ./dibab_*_all.deb

**sudo apt remove dibab** 和 **sudo apt purge dibab** 只删除软件包的文件，从不触碰配置、状态、日志和文件；清除时会列出它保留的内容。
验证程度：安装和诊断已在容器中于这四个版本上验证；容器无法验证加密保险库的挂载，也无法验证使用您自己的 Ollama 的运行。

# 文件

配置取下列顺序中第一个存在的文件，且只读取该文件：

1.  **\--config** 指定的文件；
2.  变量 **DIBAB_CONFIG** 指定的文件（当其非空时）；
3.  *$XDG_CONFIG_HOME/dibab/config.json*；当 **XDG_CONFIG_HOME** 为空或未设置时为 *~/.config/dibab/config.json*；
4.  *dibab.py* 所在文件夹中的 *config.json*。

如果选项或变量指向不存在的文件，程序以退出码 1 停止：绝不退而使用另一个文件。示例文件 *config.exemple.json* 位于程序所在文件夹；
请将其复制到上述位置之一，权限设为 600。

当配置未给出 **suivi** 的各键时，状态写在 *$XDG_STATE_HOME/dibab/* 或 *~/.local/state/dibab/* 下：*dernier_scan.json*、
*journal.jsonl*（操作日志）、*sessions/*（每次运行一份日志和一份报告）和 *dibab.log*。*rapatries.json*、*imap_deposes.json*
和锁文件 *dibab.verrou* 与 *dernier_scan.json* 放在一起。文件夹以 700 权限创建，文件以 600 权限创建。此时状态以明文保存在磁盘上：
要保存在保险库中，请设置 **suivi.fichier_date**、**suivi.journal** 和 **suivi.sessions** 键。

消息词典是程序所在文件夹中的 *modules/langues/en.txt*、*fr.txt*、*de.txt*、*es.txt* 和 *zh.txt*。

# 环境变量

**DIBAB_CONFIG**
:   配置文件的路径。

**XDG_CONFIG_HOME**、**XDG_STATE_HOME**
:   配置和默认状态的基础文件夹。

**LC_ALL**、**LC_MESSAGES**、**LANG**
:   消息语言（见 **语言**）。

IMAP 邮箱的密码从其来源的 **mot_de_passe_env** 键指定的变量读取，绝不从配置文件读取。

# 退出码

**0**
:   成功。

**1**
:   找不到配置、配置无效或缺少键；至少一个来源或文件失败；撤销只部分完成；OAuth2 授权失败；**\--diagnose** 至少有一项 **ÉCHEC**。

**2**
:   在会写入的模式之前无法确认保险库已挂载；命令行无效。

**3**
:   某个角色没有已安装的模型，或 Ollama 没有响应。

**4**
:   本机拒绝执行 **\--execute**（键 **executer_sur**）。

**5**
:   另一次运行持有锁 *dibab.verrou*。

# 示例

先检查安装，再模拟，最后实际归档：

    dibab --diagnose
    dibab --dry-run
    dibab --execute

用法语阅读同一项检查，然后撤销最近一次运行：

    LC_ALL=fr_FR.UTF-8 dibab --diagnose
    dibab --rollback

# 另请参阅

**ollama**(1)、**ssh**(1)、**findmnt**(8)、**pdftotext**(1)、**pdftoppm**(1)

项目的 README 说明从 Debian 软件包和从源代码安装的方法、配置、通过 **ssh**、IMAP 和 Google OAuth2 访问的来源，以及局限。

# 许可证

GNU Affero 通用公共许可证第 3 版。
