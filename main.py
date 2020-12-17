import logging
import os
import sqlite3
from functools import wraps

import docker
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ChatAction
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters


def connect_to_db():
    try:
        db_connection = sqlite3.connect('/telegram-bot/data/users.db')
        logging.debug("Connection to database successful.")
        return db_connection
    except sqlite3.Error as e:
        logging.error("Could not connect to database with error: {}.".format(e))
        return None


def init_database():
    db_connection = connect_to_db()
    cursor = db_connection.cursor()
    try:
        sqlite_create_table_query = "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, " \
                                    "telegram_id INTEGER NOT NULL, " \
                                    "banned INTEGER DEFAULT 0, " \
                                    "unique (telegram_id));"
        cursor.execute(sqlite_create_table_query)
        db_connection.commit()
        cursor.close()
        logging.debug("Database table created.")
    except sqlite3.Error as e:
        logging.error("Database initialization not successful with error: {}.".format(e))
    finally:
        db_connection.close()

    try:
        for u in USERS:
            insert_into_db(u)
        logging.debug("Users added to database.")
    except sqlite3.Error as e:
        logging.error("Could not finish initialization with error: {}.".format(e))


def get_users_db():
    db_connection = connect_to_db()
    cursor = db_connection.cursor()
    try:
        banned_users = []
        authorized_users = []
        sqlite_get_users = "SELECT telegram_id, banned FROM users;"
        cursor.execute(sqlite_get_users)
        users = cursor.fetchall()
        for u in users:
            if u[1] == 1:
                banned_users.append(u[0])
            else:
                authorized_users.append(u[0])
        cursor.close()
        db_connection.close()
        return authorized_users, banned_users
    except sqlite3.Error as e:
        logging.warning("Could not get users from db with error: {}.".format(e))
    finally:
        db_connection.close()


def insert_into_db(user_id, ban=False):
    db_connection = connect_to_db()
    cursor = db_connection.cursor()
    try:
        if ban:
            sqlite_insert_into = "INSERT INTO users (telegram_id, banned) VALUES (?, 1);"
            db = "banned"
        else:
            sqlite_insert_into = "INSERT INTO users (telegram_id) VALUES (?);"
            db = "users"
        cursor.execute(sqlite_insert_into, (user_id,))
        db_connection.commit()
        cursor.close()
        logging.info("Inserted user {} into {} db.".format(user_id, db))
    except:
        logging.debug("Insertion for user {} failed.".format(user_id))
    finally:
        cursor.close()
        db_connection.close()


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


def restricted_admin(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != ADMIN:
            logging.warning("Unauthorized access denied for admin function with id: {}.".format(user_id))
            update.message.reply_text("You are not allowed to do this.")
            return
        return func(update, context, *args, **kwargs)

    return wrapped


def restricted_users(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        user_name = update.effective_user.name
        if user_id not in USERS:
            logging.warning("Unauthorized access denied for user with id: {}.".format(user_id))
            update.message.reply_text("You are not allowed to do this.")

            if user_id not in BANNED and ADMIN:
                keyboard = [[InlineKeyboardButton("Yes", callback_data="add/yes/{}/{}".format(user_id, user_name))],
                            [InlineKeyboardButton("No", callback_data="add/no/{}".format(user_name))],
                            [InlineKeyboardButton("Ban", callback_data="add/ban/{}/{}".format(user_id, user_name))]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                context.bot.sendMessage(chat_id=ADMIN,
                                        text="Do you want to add {} with id {} to the authorized users?".format(
                                            user_name, user_id), reply_markup=reply_markup)
            else:
                logging.warning("User ({}) with id {} already banned.".format(user_name, user_id))
            return
        return func(update, context, *args, **kwargs)

    return wrapped


def init(update, context):
    keyboard = [[InlineKeyboardButton("Start", callback_data="start")],
                [InlineKeyboardButton("Status", callback_data="status")],
                [InlineKeyboardButton("Stop", callback_data="stop")]]
    reply_markup = ReplyKeyboardMarkup(keyboard)
    update.message.reply_text("Bot started.", reply_markup=reply_markup)


@restricted_users
def start_container(update, context):
    update_container()
    keyboard = []
    for container in CONTAINERS:
        if CONTAINERS.get(container).status != "running":
            keyboard.append([InlineKeyboardButton(container, callback_data="start/request/{}".format(container))])
    if len(keyboard) > 0:
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Which server do you want to start?", reply_markup=reply_markup)
    else:
        update.message.reply_text("Seems like all servers are already running!")


@restricted_admin
def stop_container(update, context):
    update_container()
    keyboard = []
    for container in CONTAINERS:
        if CONTAINERS.get(container).status == "running":
            keyboard.append([InlineKeyboardButton(container, callback_data="stop/request/{}".format(container))])
    if len(keyboard) > 0:
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Which server do you want to stop?", reply_markup=reply_markup)
    else:
        update.message.reply_text("Seems like all servers are already stopped!")


def answer(update, context):
    query = update.callback_query
    logging.debug("Request query: {}.".format(query.data))

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
    elif "ban" in query.data:
        request = query.data.split("/")[0]
        if request == "add":
            user_id = int(query.data.split("/")[2])
            user_name = query.data.split("/")[3]
            BANNED.append(user_id)
            insert_into_db(user_id, ban=True)
            query.edit_message_text(text="Alright, added {} to banned users.".format(user_name))
    elif "no" in query.data:
        request = query.data.split("/")[0]
        logging.debug("Denied request: {}.".format(request))
        if request == "start" or request == "stop":
            container_request = query.data.split("/")[2]
            query.edit_message_text(text="Alright, not going to {} {}.".format(request, container_request))
        elif request == "add":
            user_name = query.data.split("/")[2]
            query.edit_message_text(text="Alright, not going to {} {}.".format(request, user_name))
    elif "yes" in query.data:
        request = query.data.split("/")[0]
        logging.debug("Confirmed request: {}.".format(request))
        if request == "start" or request == "stop":
            container_request = query.data.split("/")[2]
            query.edit_message_text(text="Going to {} {} now...".format(request, container_request))
            logger.info("{} {} now!".format(request.capitalize(), container_request))
            container_to_start = CONTAINERS.get(container_request)
            if request == "start":
                container_to_start.start()
            elif request == "stop":
                container_to_start.stop()
        elif request == "add":
            user_id = int(query.data.split("/")[2])
            user_name = query.data.split("/")[3]
            query.edit_message_text(text="Added user ({}) with id {} to authroized users.".format(user_name, user_id))
            USERS.append(user_id)
            insert_into_db(user_id)
            logging.warning("Added user to authorized users with id: {}.".format(user_id))


def print_help(update, context):
    update.message.reply_text("Use /start to use this bot.")


def status(update, context):
    update_container()
    status_message = ""
    running = ":white_check_mark:"
    stopped = ":x:"

    for container in CONTAINERS:
        if CONTAINERS.get(container).status == "running":
            container_status = "running"
            icon = stopped
        else:
            icon = running
            container_status = "not running"
        status_message = status_message + icon + " " + container + " is " + container_status + "\n"
    update.message.reply_text(status_message)


def error(update, context):
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main():
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(BOT_KEY, use_context=True)

    updater.dispatcher.add_handler(CommandHandler('start', init))
    updater.dispatcher.add_handler(CommandHandler('help', print_help))
    updater.dispatcher.add_handler(MessageHandler(Filters.regex(r'^[sS]tart(?!\S)'), start_container))
    updater.dispatcher.add_handler(MessageHandler(Filters.regex(r'^[sS]tatus(?!\S)'), status))
    updater.dispatcher.add_handler(MessageHandler(Filters.regex(r'^[sS]top(?!\S)'), stop_container))
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

    USERS = []
    BANNED = []
    users_env = os.getenv("USER_IDS")
    if not users_env:
        logging.info("You have not added any user via env variables.")
    else:
        for user in users_env.split(","):
            USERS.append(int(user))
        logging.info("You have added {} users.".format(len(USERS)))
        logging.debug("Users: {}.".format(USERS))

    if not os.path.isfile("/telegram-bot/data/users.db"):
        init_database()
    else:
        authorized_us, banned_us = get_users_db()
        if len(authorized_us) > 0:
            logging.info("Found {} authorized user(s) in db.".format(len(authorized_us)))
            for authorized_u in authorized_us:
                USERS.append(authorized_u)
        else:
            logging.info("No authorized users in db found.")
        if len(banned_us) > 0:
            logging.info("Found {} banned user(s) in db.".format(len(banned_us)))
            for banned_u in banned_us:
                BANNED.append(banned_u)
        else:
            logging.info("No banned users in db found.")

    ADMIN = int(os.getenv("ADMIN_ID"))
    if not ADMIN:
        logging.info("You have not added an admin.")
    else:
        logging.debug("You have added an admin with the id: {}".format(ADMIN))
        USERS.append(int(ADMIN))

    BOT_KEY = os.getenv("BOT_KEY")
    if not BOT_KEY:
        logging.error("You have to set the BOT_KEY env in order to use this.")
        exit(1)

    main()
