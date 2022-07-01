# Contributing

aioqzone 社区期待您的贡献。

<details>

<summary>TOC</summary>

<!-- @import "[TOC]" {cmd="toc" depthFrom=2 depthTo=2 orderedList=false} -->

<!-- code_chunk_output -->

- [增补文档](#增补文档)
- [提交代码](#提交代码)

<!-- /code_chunk_output -->

</details>


## 增补文档

“文档”分为三种：项目外文档，项目内文档，docstring

### 项目外文档

指由用户编写的教程等文章。这些文章的“源”不会被收录进仓库，但在仓库的某个位置维护指向这些文章的链接。

- 任何用户都能参与
- 门槛最低，几乎没有限制。

### 项目内文档

Read Me, Contributing, Code of Conduct, 用户协议，以及 `doc/` 目录下的 rst 文档。

- 任何用户都能参与，且作为您对此社区的贡献
- 对这些文档的修改需要提交PR。
- 遵循原有语言
- 涉及 [sphinx][Sphinx] 文档时可能需要一定基础

### docstring

代码内的函数、类说明等。docstring 会在文档构建之后与项目内文档一同发布。

- 最好由开发人员编写
- 使用英语
- 需要了解 [sphinx][Sphinx]

## 提交代码

### 注意事项

在您提交 PR 之前，请阅读以下注意事项，以免您的工作蒙受损失。

1. 对于具有一定规模的问题，推荐您建立 issue 后再提交 PR。
2. 在提交 PR 之前，最好和作者取得联系。您可以通过 GitHub Issue、讨论群和邮件三种方式联系作者。
3. 在提交 PR 之前，请检查项目 **是否正在重构**（比如有正在进行的、带有 `refactor` 标签的[议题和提交](https://github.com/aioqzone/Qzone2TG/labels/refactor)）。如果您确需在重构期间提交代码，请 **务必** 提前与作者取得联系。

### 项目依赖

aioqzone 维护了若干项目用以支撑 Qzone3TG。请尽量在合适的仓库建立议题:

- [aioqzone](https://github.com/aioqzone/aioqzone): 与QQ空间登录和内容接口有关的问题请前往此仓库提交
- [aioqzone-feed](https://github.com/aioqzone/aioqzone-feed): 与说说内容后处理有关的问题请前往此仓库提交
- [QzEmoji](https://github.com/aioqzone/QzEmoji): 与表情相关的问题请前往此仓库提交
- 本仓库：转发 telegram、说说的数据库存储、应用的docker打包等。


[Sphinx]: https://www.sphinx-doc.org/ "Sphinx documentation"
