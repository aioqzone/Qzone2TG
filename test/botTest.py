import unittest

import telegram
from telegram.ext import CommandHandler, Updater

class BotTest(unittest.TestCase):
    def setUp(self):
        token = "1081188004:AAFGuWN9gXWxDPLt6Bg1iDmpZoAw4VrmxAQ"
        REQUEST_KWARGS={
            'proxy_url': 'socks5://127.0.0.1:7890',
        }
        self.updater = Updater(token=token, use_context=True, request_kwargs=REQUEST_KWARGS)

    def testSendMessage(self):
        def start(update, context):
            context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text="I'm a <b>bot</b>\nplease talk to me!", 
                parse_mode = telegram.ParseMode.HTML
                )

        dispatcher = self.updater.dispatcher
        dispatcher.add_handler(CommandHandler('start', start))
        self.updater.start_polling()
        print("start polling")
        self.updater.idle()



