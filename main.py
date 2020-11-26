import logging
import os
from functools import wraps

import docker
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ChatAction
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters


def update_container():
    containers = DOCKER_CLIENT.containers.list(all=True, filters={"label": "telegram-bot"})
    CONTAINERS.clear()
    for single_container in containers:
        container_name = single_container.labels
        container_name = container_name.get("telegram-bot")
        CONTAINERS.update({container_name: single_container})


def send_typing_action(func):
    @wraps(func)
    def command_func(update, context, *args, **kwargs):
        context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)
        return func(update, context, *args, **kwargs)

    return command_func


def restricted(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != int(ADMIN):
            logging.warning("Unauthorized access denied for %s." % user_id)
            update.message.reply_text("You are not allowed to do this.")
            return
        return func(update, context, *args, **kwargs)

    return wrapped


def init(update, context):
    keyboard = [[InlineKeyboardButton("Start", callback_data="start")],
                [InlineKeyboardButton("Status", callback_data="status")],
                [InlineKeyboardButton("Stop (Admin only)", callback_data="stop")]]
    reply_markup = ReplyKeyboardMarkup(keyboard)
    update.message.reply_text("Bot started.", reply_markup=reply_markup)


def start_container(update, context):
    update_container()
    keyboard = []
    for container in CONTAINERS:
        if CONTAINERS.get(container).status != "running":
            keyboard.append([InlineKeyboardButton(container, callback_data="start/request/" + container)])
    if len(keyboard) > 0:
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Which server do you want to start?", reply_markup=reply_markup)
    else:
        update.message.reply_text("Seems like all servers are already running!")


@restricted
def stop_container(update, context):
    update_container()
    keyboard = []
    for container in CONTAINERS:
        if CONTAINERS.get(container).status == "running":
            keyboard.append([InlineKeyboardButton(container, callback_data="stop/request/" + container)])
    if len(keyboard) > 0:
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Which server do you want to stop?", reply_markup=reply_markup)
    else:
        update.message.reply_text("Seems like all servers are already stopped!")


def answer(update, context):
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    query.answer()

    update_container()
    if "start/request" in query.data:
        container_request = query.data.split("/")[2]
        container = CONTAINERS.get(container_request)
        if container:
            if container.status == "running":
                query.edit_message_text(text="{} is already running, go and have fun!".format(container_request))
                return
            else:
                keyboard = [[InlineKeyboardButton("Yes", callback_data='start/yes/' + container_request),
                             InlineKeyboardButton("No", callback_data='start/no/' + container_request)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                query.edit_message_text(text="Do you really want to start {}?".format(container_request),
                                        reply_markup=reply_markup)
        else:
            query.edit_message_text(text="No servers found with this name.")
            return
    if "stop/request" in query.data:
        container_request = query.data.split("/")[2]
        container = CONTAINERS.get(container_request)
        if container:
            if container.status != "running":
                query.edit_message_text(text="{} is already stopped, you can start it now!".format(container_request))
                return
            else:
                keyboard = [[InlineKeyboardButton("Yes", callback_data='stop/yes/' + container_request),
                             InlineKeyboardButton("No", callback_data='stop/no/' + container_request)]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                query.edit_message_text(text="Do you really want to stop {}?".format(container_request),
                                        reply_markup=reply_markup)
        else:
            query.edit_message_text(text="No servers found with this name.")
            return
    elif 'no' in query.data:
        request = query.data.split("/")[0]
        container_request = query.data.split("/")[2]
        query.edit_message_text(text="Alright, not going to {} {}.".format(request, container_request))
    elif 'yes' in query.data:
        request = query.data.split("/")[0]
        container_request = query.data.split("/")[2]
        query.edit_message_text(text="Going to {} {} now...".format(request, container_request))
        logger.info("{} {} now!".format(request.capitalize(), container_request))
        container_to_start = CONTAINERS.get(container_request)
        if request == "start":
            container_to_start.start()
        elif request == "stop":
            container_to_start.stop()


def help(update, context):
    update.message.reply_text("Use /start to use this bot. \n"
                              "Use /status to check the status of the servers.")


def status(update, context):
    update_container()
    status_message = ""
    for container in CONTAINERS:
        if CONTAINERS.get(container).status == "running":
            container_status = "running"
        else:
            container_status = "not running"
        status_message = status_message + container + " is " + container_status + ".\n"
    update.message.reply_text(status_message)


def error(update, context):
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main():
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(BOT_KEY, use_context=True)

    updater.dispatcher.add_handler(CommandHandler('start', init))
    updater.dispatcher.add_handler(CommandHandler('help', help))
    updater.dispatcher.add_handler(CommandHandler('status', status))
    updater.dispatcher.add_handler(MessageHandler(Filters.regex(r'^[sS]tart\s'), start_container))
    updater.dispatcher.add_handler(MessageHandler(Filters.regex(r'^[sS]tatus\s'), status))
    updater.dispatcher.add_handler(MessageHandler(Filters.regex(r'^[sS]top\s'), stop_container))
    updater.dispatcher.add_handler(CallbackQueryHandler(answer))
    updater.dispatcher.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until the user presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT
    updater.idle()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    DOCKER_CLIENT = docker.DockerClient(base_url='unix://var/run/docker.sock')
    CONTAINERS = {}
    update_container()
    logging.info("Found %d container to handle." % len(CONTAINERS))

    ADMIN = os.getenv("ADMIN_ID")
    if not ADMIN:
        logging.info("You have not added an admin.")
    else:
        logging.debug("You have added an admin with the ID: %s" % ADMIN)

    BOT_KEY = os.getenv("BOT_KEY")
    if not BOT_KEY:
        logging.error("You have to set the BOT_KEY env in order to use this.")
        exit(1)

    main()
