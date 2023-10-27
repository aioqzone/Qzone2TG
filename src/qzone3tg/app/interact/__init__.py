"""This module defines an app that interact with user using /command and inline markup buttons."""
import asyncio
import re
from contextlib import suppress
from typing import Callable

import aiogram.filters as filter
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.command import CommandObject
from aiogram.types import BotCommand, FSInputFile, Message
from aiogram.utils.formatting import BotCommand as CommandText
from aiogram.utils.formatting import Url as UrlText
from aiogram.utils.formatting import as_key_value, as_list, as_marked_section
from aioqzone.model import LikeData

from qzone3tg import CHANNEL, DISCUSS, DOCUMENT
from qzone3tg.app.storage.blockset import BlockSet
from qzone3tg.settings import Settings, WebhookConf

from ..base import BaseApp
from ._block import command_block
from ._conversation.emoji import command_em
from .types import SerialCbData


class InteractApp(BaseApp):
    commands: list[BotCommand] = [
        BotCommand(command="start", description="刷新"),
        BotCommand(command="status", description="获取运行状态"),
        BotCommand(command="up_login", description="密码登录"),
        BotCommand(command="qr_login", description="二维码登录"),
        BotCommand(command="like", description="点赞指定的说说"),
        BotCommand(command="help", description="帮助"),
        BotCommand(command="block", description="黑名单管理"),
        command_em,
        command_block,
    ]

    def __init__(self, conf: Settings) -> None:
        super().__init__(conf)

    # --------------------------------
    #            hook init
    # --------------------------------
    from ._button import queueevent_hook as _sub_queueevent

    def init_queue(self):
        super().init_queue()
        self.dyn_blockset = BlockSet(self.engine)

    def init_hooks(self):
        from ._hook import add_qr_impls, add_up_impls

        add_qr_impls(self)
        add_up_impls(self)
        super().init_hooks()

    async def __aenter__(self):
        await super().__aenter__()
        self.register_handlers()
        return self

    def register_handlers(self):
        from ._button import build_router as _button_router
        from ._conversation.emoji import build_router as _emoji_router

        # build chat filters
        CA = F.from_user.id.in_({self.conf.bot.admin})

        for command in self.commands:
            self.dp.message.register(
                getattr(self, command.command, self.help),
                CA,
                filter.Command(command),
            )

        self.dp.callback_query.register(
            self.btn_qr,
            SerialCbData.filter(F.command == "qr"),
            SerialCbData.filter(F.sub_command.in_({"refresh", "cancel"})),
        )
        self.dp.callback_query.register(
            self.btn_like,
            SerialCbData.filter(F.command == "like"),
            SerialCbData.filter(F.sub_command.regexp(r"-?\d+")),
        )

        self.dp.include_routers(_emoji_router(self), _button_router(self))

    async def set_commands(self):
        try:
            await self.bot.set_my_commands(self.commands)
        except:
            self.log.error("Error in setting commands", exc_info=True)

    async def _start_webhook(self, conf: WebhookConf):
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        from aiohttp import web

        @self.dp.startup()
        async def on_startup(bot: Bot) -> None:
            # If you have a self-signed SSL certificate, then you will need to send a public
            # certificate to Telegram
            cert = FSInputFile(conf.cert) if conf.cert else None
            await bot.set_webhook(
                str(conf.destination),
                certificate=cert,
                max_connections=conf.max_connections,
                drop_pending_updates=conf.drop_pending_updates,
                secret_token=conf.secret_token,
            )

        # Create aiohttp.web.Application instance
        app = web.Application()

        # Create an instance of request handler,
        # aiogram has few implementations for different cases of usage
        # In this example we use SimpleRequestHandler which is designed to handle simple cases
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=self.dp, bot=self.bot, secret_token=conf.secret_token
        )
        # Register webhook handler on application
        webhook_requests_handler.register(app, path=conf.destination.path or "/")

        # Mount dispatcher startup and shutdown hooks to aiohttp application
        setup_application(app, self.dp, bot=self.bot)

        # And finally start webserver
        try:
            await web._run_app(app, host="0.0.0.0", port=conf.port)
        except (web.GracefulExit, KeyboardInterrupt):
            pass

    async def run(self):
        """
        :meth:`InteractApp.run` will start polling or webhook, run its own preparations,
        and call :meth:`BaseApp.run`.

        :return: None
        """
        await asyncio.gather(
            self.set_commands(),
            self.dyn_blockset.create(),
        )
        # 加载动态黑名单
        self.blockset.update(await self.dyn_blockset.all())
        return await super().run()

    async def idle(self):
        conf = self.conf.bot.init_args
        if isinstance(conf, WebhookConf):
            return await self._start_webhook(conf)

        info = await self.bot.get_webhook_info()
        if info.url:
            await self.bot.delete_webhook(drop_pending_updates=False)
            self.log.warning("webhook deleted.")
        await self.dp.start_polling(self.bot, **conf.model_dump())

    # --------------------------------
    #            command
    # --------------------------------
    async def start(self, message: Message, command: CommandObject):
        chat = message.chat

        self.log.debug("Start! chat=%d", chat.id)
        if self.ch_fetch._futs:
            self.log.warning("有正在进行的抓取任务")
            self.ch_fetch.clear()
        self.ch_fetch.add_awaitable(self._fetch(chat.id))

    async def help(self, message: Message, command: CommandObject):
        chat = message.chat

        help_section = as_marked_section(
            "命令：", *(as_key_value(CommandText(c.command), c.description) for c in self.commands)
        )
        brand_section = as_marked_section(
            "其他帮助：",
            as_key_value("官方频道", UrlText(CHANNEL)),
            as_key_value("讨论群", UrlText(DISCUSS)),
            as_key_value("文档", UrlText(f"{DOCUMENT}/usage.html")),
        )

        await self.bot.send_message(
            chat.id, **as_list(help_section, brand_section, sep="\n\n").as_kwargs()
        )

    async def status(self, message: Message, command: CommandObject):
        chat = message.chat
        assert message.text

        match command.args:
            case "debug":
                await super().status(chat.id, debug=True)
            case _:
                await super().status(chat.id)

    async def up_login(self, message: Message, command: CommandObject):
        await self._uplogin.new_cookie()
        # `LoginSuccess` hooks will restart heartbeat

    async def qr_login(self, message: Message, command: CommandObject):
        await self._qrlogin.new_cookie()

    async def like(self, message: Message, command: CommandObject):
        assert message
        reply = message.reply_to_message
        if not reply:
            await message.reply("使用 /like 时，您需要回复一条消息。")
            return

        async def query_likedata(mid: int):
            feed = await self.Mid2Feed(reply.message_id)
            if not feed:
                await message.reply(f"未找到该消息，可能已超出 {self.conf.bot.storage.keepdays} 天。")
                return

            if feed.unikey is None:
                await message.reply("该说说不支持点赞。")
                return

            return LikeData(
                unikey=str(feed.unikey),
                curkey=str(feed.curkey) or LikeData.persudo_curkey(feed.uin, feed.abstime),
                appid=feed.appid,
                typeid=feed.typeid,
                fid=feed.fid,
                abstime=feed.abstime,
            )

        async def like_trans(likedata: LikeData):
            try:
                succ = await self.qzone.internal_dolike_app(
                    likedata.appid, likedata.unikey, likedata.curkey, True
                )
            except:
                self.log.error("点赞失败", exc_info=True)
                succ = False
            if succ:
                await message.reply("点赞成功")
            else:
                await message.reply("点赞失败")

        likedata = await query_likedata(reply.message_id)
        if likedata is None:
            return
        await like_trans(likedata)

    async def input(
        self,
        prompt_message: Message,
        pattern: re.Pattern[str] | str,
        retry_prompt: str,
        timeout: float,
        *,
        filters: tuple[Callable, ...] = (),
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> str | None:
        self.dp.include_router(router := Router(name="input"))
        fut: asyncio.Future[str] = (loop or asyncio.get_event_loop()).create_future()
        fut.add_done_callback(lambda _: self.dp.sub_routers.remove(router))

        @router.message(*filters, F.text.regexp(pattern).as_("match"))
        async def _valid_input(message: Message, match: re.Match[str]):
            fut.set_result(ret := match.group(1))
            prompt_message.reply(f"合法的输入：{ret}")

        @router.message(*filters)
        async def _invalid_input(message: Message):
            await message.reply(retry_prompt.format(text=message.text))

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.CancelledError:
            await prompt_message.reply(f"已取消")
        except asyncio.TimeoutError:
            await prompt_message.reply(f"在{timeout}秒内未取得符合条件的输入。")
        finally:
            if not fut.done():
                fut.cancel()

        with suppress(TelegramBadRequest):
            await prompt_message.delete_reply_markup()
        return None

    # --------------------------------
    #              query
    # --------------------------------
    from ._block import block
    from ._button import btn_like, btn_qr
    from ._conversation.emoji import em, input_eid
