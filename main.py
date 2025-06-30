import os
import discord
import dotenv


class QOTDClient(discord.Client):
    async def on_ready(self):
        print(f"Ready as {self.user}.")

    async def on_message(self, message):
        print(f"Message recieved from {message.author}: {message.content}")


def main():
    dotenv.load_dotenv()

    intents = discord.Intents.default()
    intents.message_content = True

    client = QOTDClient(intents=intents)
    client.run(os.environ.get("TOKEN"))

if __name__ == "__main__":
    main()