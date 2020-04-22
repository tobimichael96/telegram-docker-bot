# telegram docker bot

This is a telegram bot which listens for messages and start docker container.

### Use case

If you are running Minecraft or Factorio or TeamSpeak3 container and you don't need them
all the time you might want to stop them in order to save (computing) power, but if you
need them, you don't want to log in to the server and time those commands in.

That's why this bot exists: You can write this bot a message and it start the container.

### Configuration

You have to pass the container the Docker socket.

You have to add the Telegrambot-Key via environment variable.

### Sample docker-compose file

```
app:
   image: ausraster/telegram-docker-bot
   container_name: telegram-docker-bot
   environment:
     - ADMIN_ID=0123456789
     - BOT_KEY=0123456789:abcdefghijklmn
   volumes:
     - /var/run/docker.sock:/var/run/docker.sock
```