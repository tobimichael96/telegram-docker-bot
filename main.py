import logging
import os
from functools import wraps
import sqlite3

import docker
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ChatAction
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters


def update_container():
	CONTAINERS.clear()
	containers = DOCKER_CLIENT.containers.list(all=True, filters={"label": "telegram-bot"})
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


def admin_restricted(func):
	@wraps(func)
	def wrapped(update, context, *args, **kwargs):
		user_id = update.effective_user.id
		if user_id != ADMIN:
			logging.error("Unauthorized access denied for %s." % user_id)
			return
		return func(update, context, *args, **kwargs)

	return wrapped


def user_restricted(func):
	@wraps(func)
	def wrapped(update, context, *args, **kwargs):
		user_id = update.effective_user.id
		if user_id not in ALLOWED_USERS:
			logging.error("User %s not allowed." % user_id)
			keyboard = [[InlineKeyboardButton('Yes', callback_data='add_request/' + str(user_id))],
			            [InlineKeyboardButton('No', callback_data='no')]]
			reply_markup = InlineKeyboardMarkup(keyboard)
			update.message.reply_text(text="Do you want to request to get added to the allowed users?",
			                          reply_markup=reply_markup)
			return
		return func(update, context, *args, **kwargs)

	return wrapped


@user_restricted
def start(update, context):
	keyboard = [[InlineKeyboardButton("Start", callback_data="start")],
	            [InlineKeyboardButton("Status", callback_data="status")]]
	reply_markup = ReplyKeyboardMarkup(keyboard)
	update.message.reply_text("Bot started.", reply_markup=reply_markup)


@user_restricted
def menu(update, context):
	update_container()
	keyboard = []
	for container in CONTAINERS:
		if CONTAINERS.get(container).status != "running":
			keyboard.append([InlineKeyboardButton(container, callback_data="start_request/" + container)])
	if len(keyboard) > 0:
		reply_markup = InlineKeyboardMarkup(keyboard)
		update.message.reply_text("Which server do you want to start?", reply_markup=reply_markup)
	else:
		update.message.reply_text("Seems like all servers are already running!")


def answer(update, context):
	query = update.callback_query

	# CallbackQueries need to be answered, even if no notification to the user is needed
	# Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
	query.answer()

	update_container()

	if "add_request" in query.data:
		logging.info(update)
		query.edit_message_text(text="Your request was sent to the Admin.")
		keyboard = [[InlineKeyboardButton('Yes', callback_data='add_user/' + str(update.effective_user.id)),
		             InlineKeyboardButton('No', callback_data='denied_user')]]
		reply_markup = InlineKeyboardMarkup(keyboard)
		context.bot.send_message(chat_id=ADMIN, text="Do you want to add %s to the allowed users?"
		                                             % update.effective_user.id, reply_markup=reply_markup)
	elif "add_user" in query.data:
		if update.effective_user.id == ADMIN:
			member = query.data.split("/")[1]
			logging.info("Added new user to allowed list: %s." % member)
			context.bot.send_message(chat_id=member, text="You were added to the allowed user group.")
			query.edit_message_text(text="User %s was added to allowed user group." % member)
			ALLOWED_USERS.append(int(member))
			write_to_db(int(member))
		else:
			logging.error("Not admin user (%s) tried to gain more power." % update.effective_user.id)
	elif "denied_user" in query.data:
		query.edit_message_text(text="User was not added to allowed user group.")
		logging.info("User was not added to allowed user group.")
	elif "start_request" in query.data:
		container_request = query.data.split("/")[1]
		container = CONTAINERS.get(container_request)
		if container:
			if container.status == "running":
				query.edit_message_text(text="%s is already running, go and have fun!" % container_request)
			else:
				keyboard = [[InlineKeyboardButton('Yes', callback_data='yes/' + container_request),
				             InlineKeyboardButton('No', callback_data='no')]]
				reply_markup = InlineKeyboardMarkup(keyboard)
				query.edit_message_text(text="Do you really want to start the %s server?" %
				                             container_request, reply_markup=reply_markup)
		else:
			query.edit_message_text(text="No servers found with this name.")
	elif 'no' in query.data:
		query.edit_message_text(text="Alright, nothing to do for me. I like that!")
	elif 'yes' in query.data:
		container_request = query.data.split("/")[1]
		query.edit_message_text(text="Going to start %s now..." % container_request)
		logger.info("Starting %s now!" % container_request)
		container_to_start = CONTAINERS.get(container_request)
		container_to_start.start()


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


@admin_restricted
def stop(update, context):
	# TODO: implement admin function to stop container
	update.message.reply_text("Will be implemented soon!")


def main():
	# Create the Updater and pass it your bot's token.
	# Make sure to set use_context=True to use the new context based callbacks
	# Post version 12 this will no longer be necessary
	updater = Updater(BOT_KEY, use_context=True)

	updater.dispatcher.add_handler(CommandHandler('start', start))
	updater.dispatcher.add_handler(CommandHandler('help', help))
	updater.dispatcher.add_handler(CommandHandler('status', status))
	updater.dispatcher.add_handler(CommandHandler('stop', stop))
	updater.dispatcher.add_handler(MessageHandler(Filters.regex(r'[sS]tart'), menu))
	updater.dispatcher.add_handler(MessageHandler(Filters.regex(r'[sS]tatus'), status))
	updater.dispatcher.add_handler(MessageHandler(Filters.regex(r'[sS]top'), stop))
	updater.dispatcher.add_handler(CallbackQueryHandler(answer))
	updater.dispatcher.add_error_handler(error)

	# Start the Bot
	updater.start_polling()

	# Run the bot until the user presses Ctrl-C or the process receives SIGINT,
	# SIGTERM or SIGABRT
	updater.idle()


def write_to_db(user_id):
	cursor = DB_CON.cursor()
	cursor.execute('INSERT INTO allowed_users (telegram_user_id) VALUES (?)', (user_id,))
	DB_CON.commit()


def read_db():
	cursor = DB_CON.cursor()
	cursor.execute('SELECT * FROM allowed_users')
	users = cursor.fetchall()
	for line in users:
		logging.info(line[1])
	DB_CON.commit()


def init_db():
	cursor = DB_CON.cursor()
	cursor.execute('''CREATE TABLE  IF NOT EXISTS allowed_users 
	(user_id INTEGER PRIMARY KEY, telegram_user_id INT NOT NULL)''')
	cursor.execute('INSERT INTO allowed_users (telegram_user_id) VALUES (?)', (ADMIN,))
	cursor.execute('SELECT * FROM allowed_users')
	DB_CON.commit()


if __name__ == '__main__':
	logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
	logger = logging.getLogger(__name__)

	DOCKER_CLIENT = docker.DockerClient(base_url='unix://var/run/docker.sock')
	CONTAINERS = {}
	update_container()
	logging.info("Found %d container to handle." % len(CONTAINERS))

	ALLOWED_USERS = []
	ADMIN = os.getenv("ADMIN_ID")
	if not ADMIN:
		logging.error("You have not added an admin.")
		exit(1)
	else:
		logging.debug("You have added an admin with the ID: %s" % ADMIN)
		ADMIN = int(ADMIN)
		ALLOWED_USERS.append(ADMIN)

	DB_CON = sqlite3.connect('telegram-docker-bot/db/allowed_users.db')
	if os.getenv("FIRST_RUN"):
		init_db()
	read_db()

	BOT_KEY = os.getenv("BOT_KEY")
	if not BOT_KEY:
		logging.error("You have to set the BOT_KEY env in order to use this.")
		exit(1)

	main()
