# Contributing

aioqzone 社区期待您的贡献。

## 建立议题

任何人都可以发起 issue. 这包括 BUG 反馈，新功能申请，安全问题等。**对使用方法的咨询不在此列，而应该前往讨论群。**

## 注意事项

在您提交 PR 之前，有一些问题需要注意，以免您的工作蒙受损失。

1. 对于具有一定规模的问题，推荐您建立 issue 后再提交 PR。
2. 在提交 PR 之前，最好和作者取得联系。您可以通过 GitHub Issue、讨论群和邮件三种方式联系作者。
3. 在提交 PR 之前，请检查项目 **是否正在重构**。如有正在进行的带有 `refactor` 标签的[议题和提交](https://github.com/aioqzone/Qzone2TG/labels/refactor)。如果您确需在重构期间提交代码，请 **务必** 提前与作者取得联系。

## 常识和规范

在提交涉及较深的 PR 之前，您可能需要了解 Qzone3TG 的基本结构和设计准则。

- Qzone3TG 依赖于 [aioqzone](https://github.com/aioqzone/aioqzone) 和 [aioqzone-feed](https://github.com/aioqzone/aioqzone-feed)。与QQ空间登录和内容接口有关的问题请前往 aioqzone，与说说内容后处理有关的问题请前往 aioqzone-feed。与表情相关的问题请前往 [QzEmoji](https://github.com/aioqzone/QzEmoji)。涉及转发 telegram、说说的数据库存储、应用的docker打包等问题确属本仓库。

- 选择依赖。如果实现同一功能有多个依赖可供选择，请尽量选择能被更多的包所使用的依赖。比如，QzEmoji 和 Qzone3TG 都使用 `sqlalchemy`，比如我们舍弃 `aiohttp` 而选用 `httpx` (为了和 `python-telegram-bot` v20 共用 `httpx`)。
