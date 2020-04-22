import logging
import os
from functools import wraps

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


def restricted(func):
	@wraps(func)
	def wrapped(update, context, *args, **kwargs):
		user_id = update.effective_user.id
		if user_id != int(ADMIN):
			logging.error("Unauthorized access denied for %s." % user_id)
			return
		return func(update, context, *args, **kwargs)

	return wrapped


def start(update, context):
	keyboard = [[InlineKeyboardButton("Start", callback_data="start")],
	            [InlineKeyboardButton("Status", callback_data="status")]]
	reply_markup = ReplyKeyboardMarkup(keyboard)
	update.message.reply_text("Bot started.", reply_markup=reply_markup)


def menu(update, context):
	update_container()
	keyboard = []
	for container in CONTAINERS:
		if CONTAINERS.get(container).status != "running":
			keyboard.append([InlineKeyboardButton(container, callback_data="request/" + container)])
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
	if "request" in query.data:
		container_request = query.data.split("/")[1]
		container = CONTAINERS.get(container_request)
		if container:
			if container.status == "running":
				query.edit_message_text(text="%s is already running, go and have fun!" % container_request)
				return
			else:
				keyboard = [[InlineKeyboardButton("Yes", callback_data='yes/' + container_request),
				             InlineKeyboardButton("No", callback_data='no/' + container_request)]]
				reply_markup = InlineKeyboardMarkup(keyboard)
				query.edit_message_text(text="Do you really want to start the %s server?" %
				                             container_request, reply_markup=reply_markup)
		else:
			query.edit_message_text(text="No servers found with this name.")
			return
	elif 'no' in query.data:
		container_request = query.data.split("/")[1]
		query.edit_message_text(text="Alright, not going to start %s." % container_request)
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


@restricted
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
