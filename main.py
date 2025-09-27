from logger import logger
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from config import config
from database import engine, Base
from handlers import main_router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

# Create database tables
Base.metadata.create_all(bind=engine)

# Just when we need proxy
if config.PROXY_URL:
    session = AiohttpSession(
        proxy=config.PROXY_URL
    )

    # Create bot with proxy session
    bot = Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode='HTML')
    )

# Create bot and dispatcher
else:
    
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# Add router
dp.include_router(main_router)

async def on_startup(bot: Bot):
    #await bot.set_webhook(config.WEBHOOK_URL)
    logger.info("Bot started!")

async def on_shutdown(bot: Bot):
    #await bot.delete_webhook()
    logger.info("Bot stopped!")

def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    
    webhook_requests_handler.register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    
    web.run_app(app, host=config.WEBAPP_HOST, port=config.WEBAPP_PORT)

if __name__ == "__main__":
    main()