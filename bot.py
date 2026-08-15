import os
import glob
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import yt_dlp

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = "@yoursoundcloudbot"

if not BOT_TOKEN:
    raise ValueError("Ошибка: Переменная окружения BOT_TOKEN не задана!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class DownloadStates(StatesGroup):
    waiting_for_choice = State()

def get_download_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎵 Скачать песню", callback_data="dl_song")],
        [InlineKeyboardButton(text="💽 Скачать альбом", callback_data="dl_album")],
        [InlineKeyboardButton(text="📜 Скачать плейлист", callback_data="dl_playlist")]
    ])
    return keyboard

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        f"Привет! Отправь мне ссылку из SoundCloud, выбери вариант загрузки, и я пришлю MP3 с водяным знаком {BOT_USERNAME}."
    )

@dp.message(F.text.contains("soundcloud.com"))
async def process_soundcloud_link(message: types.Message, state: FSMContext):
    # Сохраняем ссылку в состоянии пользователя
    await state.update_data(link=message.text.strip())
    await state.set_state(DownloadStates.waiting_for_choice)
    
    await message.answer(
        "Что именно ты хочешь скачать по этой ссылке?",
        reply_markup=get_download_keyboard()
    )

@dp.callback_query(DownloadStates.waiting_for_choice, F.data.startswith("dl_"))
async def handle_download_choice(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    data = await state.get_data()
    url = data.get("link")
    choice = callback.data
    
    # Удаляем меню кнопок, чтобы не кликали повторно
    await callback.message.edit_text("🔄 Начинаю обработку запроса...")
    
    # Режим скачивания только 1 трека или списка
    noplaylist = True if choice == "dl_song" else False

    # Префикс папки для изоляции файлов разных пользователей
    user_dir = f"dl_{callback.from_user.id}_{callback.message.message_id}"
    os.makedirs(user_dir, exist_ok=True)

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{user_dir}/%(title)s.%(ext)s',
        'noplaylist': noplaylist,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
    }

    loop = asyncio.get_event_loop()

    try:
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=True)

        info = await loop.run_in_executor(None, download)
        mp3_files = glob.glob(f"{user_dir}/*.mp3")

        if not mp3_files:
            await callback.message.edit_text("❌ Не удалось найти MP3 файлы по этой ссылке.")
            await state.clear()
            return

        await callback.message.edit_text(f"📤 Отправляю файлы (всего: {len(mp3_files)})...")

        for file_path in mp3_files:
            original_filename = os.path.basename(file_path)
            clean_name = os.path.splitext(original_filename)[0]
            
            # Добавляем юзернейм бота к названию
            final_title = f"{clean_name} {BOT_USERNAME}"
            
            audio = FSInputFile(file_path)
            await callback.message.answer_audio(
                audio=audio, 
                title=final_title
            )
            # Небольшая задержка, чтобы Telegram не заблокировал за спам при отправке большого плейлиста
            await asyncio.sleep(1)

        await callback.message.answer("✅ Все треки успешно отправлены!")

    except Exception as e:
        logging.error(f"Error during download: {e}")
        await callback.message.answer("❌ Произошла ошибка при скачивании.")
    
    finally:
        # Полная очистка временной папки с файлами
        for f in glob.glob(f"{user_dir}/*"):
            os.remove(f)
        os.rmdir(user_dir)
        await state.clear()

@dp.message()
async def unknown_message(message: types.Message):
    await message.answer("Отправь мне ссылку на SoundCloud!")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
  
asyncio.run(main())
