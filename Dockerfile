FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install discord.py python-dotenv
COPY . .
CMD ["python", "bot.py"]
