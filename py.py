import os
import json
import datetime
import uuid
import asyncio
from typing import Dict, List, Optional
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram import Router

# Загрузка конфиденциальных данных
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ Токен бота не найден! Проверьте файл .env")
    exit()

ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '1862652984').split(',') if id.strip()]

# Константы
MATERIALS_FILE = "data/materials.json"
STATS_FILE = "data/statistics.json"
MEDIA_DIR = "static/media"
os.makedirs("data", exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

# Предметы и группы
SUBJECTS = {
    "информатика": "Информатика",
    "архитектура": "Архитектура", 
    "ит": "ИТ",
    "мдк": "МДК 05.01"
}

INFORMATICS_GROUPS = ["11", "12", "13", "14", "15", "16", "17"]

# Типы материалов для предметов
SUBJECT_TYPES = {
    "архитектура": ["📚 Лекции", "📝 Практические работы"],
    "мдк": ["📚 Лекции", "📝 Практические работы"]
}

# Инициализация бота
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# Состояния FSM для добавления материалов
class AddMaterialStates(StatesGroup):
    waiting_subject = State()
    waiting_group = State()
    waiting_type = State()
    waiting_title = State()
    waiting_description = State()
    waiting_file = State()

# Модели данных
class Material:
    def __init__(self, material_id: str, title: str, subject: str, group: str = "", material_type: str = "", description: str = "", 
                 file_path: str = None, date_added: str = None):
        self.id = material_id
        self.title = title
        self.subject = subject
        self.group = group
        self.material_type = material_type
        self.description = description
        self.file_path = file_path
        self.date_added = date_added or datetime.date.today().isoformat()
    
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "subject": self.subject,
            "group": self.group,
            "material_type": self.material_type,
            "description": self.description,
            "file_path": self.file_path,
            "date_added": self.date_added
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            material_id=data["id"],
            title=data["title"],
            subject=data["subject"],
            group=data.get("group", ""),
            material_type=data.get("material_type", ""),
            description=data.get("description", ""),
            file_path=data.get("file_path"),
            date_added=data.get("date_added")
        )

# Модель для статистики
class Statistics:
    def __init__(self):
        self.file_path = STATS_FILE
        self.data = self.load_data()
    
    def load_data(self) -> dict:
        """Загрузка статистики из файла"""
        default_data = {
            "total_users": 0,
            "active_users": [],
            "daily_stats": {},
            "material_views": {},
            "subject_views": {},
            "user_actions": {}
        }
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"❌ Ошибка загрузки статистики: {e}")
        return default_data
    
    def save_data(self):
        """Сохранение статистики в файл"""
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения статистики: {e}")
            return False
    
    def register_user(self, user_id: int):
        """Регистрация пользователя"""
        today = datetime.date.today().isoformat()
        user_id_str = str(user_id)
        
        # Общая статистика
        if user_id_str not in self.data["active_users"]:
            self.data["active_users"].append(user_id_str)
        
        self.data["total_users"] = len(self.data["active_users"])
        
        # Дневная статистика
        if today not in self.data["daily_stats"]:
            self.data["daily_stats"][today] = {
                "new_users": 0,
                "active_users": [],
                "actions": 0
            }
        
        daily = self.data["daily_stats"][today]
        if user_id_str not in daily["active_users"]:
            daily["new_users"] += 1
            daily["active_users"].append(user_id_str)
        
        self.save_data()
    
    def register_action(self, user_id: int, action_type: str, target: str = None):
        """Регистрация действия пользователя"""
        today = datetime.date.today().isoformat()
        user_id_str = str(user_id)
        
        # Регистрируем пользователя
        self.register_user(user_id)
        
        # Обновляем дневную статистику
        if today in self.data["daily_stats"]:
            self.data["daily_stats"][today]["actions"] += 1
        
        # Статистика по материалам
        if action_type == "material_view" and target:
            if target not in self.data["material_views"]:
                self.data["material_views"][target] = 0
            self.data["material_views"][target] += 1
        
        # Статистика по предметам
        if action_type == "subject_view" and target:
            if target not in self.data["subject_views"]:
                self.data["subject_views"][target] = 0
            self.data["subject_views"][target] += 1
        
        # Статистика по пользователям
        if user_id_str not in self.data["user_actions"]:
            self.data["user_actions"][user_id_str] = {
                "first_seen": today,
                "last_seen": today,
                "total_actions": 0,
                "action_types": {}
            }
        
        user_stats = self.data["user_actions"][user_id_str]
        user_stats["last_seen"] = today
        user_stats["total_actions"] += 1
        
        if action_type not in user_stats["action_types"]:
            user_stats["action_types"][action_type] = 0
        user_stats["action_types"][action_type] += 1
        
        self.save_data()
    
    def get_daily_stats(self, days: int = 7) -> List[dict]:
        """Получить статистику за последние N дней"""
        result = []
        today = datetime.date.today()
        
        for i in range(days):
            date = today - datetime.timedelta(days=i)
            date_str = date.isoformat()
            
            if date_str in self.data["daily_stats"]:
                daily = self.data["daily_stats"][date_str]
                result.append({
                    "date": date_str,
                    "new_users": daily["new_users"],
                    "active_users": len(daily["active_users"]),
                    "actions": daily["actions"]
                })
            else:
                result.append({
                    "date": date_str,
                    "new_users": 0,
                    "active_users": 0,
                    "actions": 0
                })
        
        return result
    
    def get_popular_materials(self, limit: int = 10) -> List[dict]:
        """Получить самые популярные материалы"""
        materials = sorted(
            self.data["material_views"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
        return [{"material_id": mat_id, "views": views} for mat_id, views in materials]
    
    def get_popular_subjects(self) -> List[dict]:
        """Получить статистику по предметам"""
        return [
            {"subject": subject, "views": views}
            for subject, views in self.data["subject_views"].items()
        ]
    
    def get_active_users_count_today(self) -> int:
        """Получить количество активных пользователей сегодня"""
        today = datetime.date.today().isoformat()
        if today in self.data["daily_stats"]:
            return len(self.data["daily_stats"][today]["active_users"])
        return 0

# Функции работы с данными
class DataManager:
    @staticmethod
    def load_json(file_path: str, default=None):
        if default is None:
            default = {}
        try:
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки {file_path}: {e}")
        return default
    
    @staticmethod
    def save_json(data, file_path: str):
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Ошибка сохранения {file_path}: {e}")
            return False

class MaterialManager:
    def __init__(self):
        self.file_path = MATERIALS_FILE
    
    def get_all_materials(self) -> Dict[str, dict]:
        return DataManager.load_json(self.file_path, {})
    
    def save_materials(self, materials: Dict[str, dict]):
        return DataManager.save_json(materials, self.file_path)
    
    def add_material(self, material: Material) -> bool:
        materials = self.get_all_materials()
        materials[material.id] = material.to_dict()
        return self.save_materials(materials)
    
    def delete_material(self, material_id: str) -> bool:
        materials = self.get_all_materials()
        if material_id in materials:
            if materials[material_id].get("file_path"):
                try:
                    file_path = os.path.join(MEDIA_DIR, materials[material_id]["file_path"])
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"✅ Файл {file_path} удален")
                except Exception as e:
                    print(f"Ошибка удаления файла: {e}")
            del materials[material_id]
            return self.save_materials(materials)
        return False
    
    def get_material(self, material_id: str) -> Optional[Material]:
        materials = self.get_all_materials()
        material_data = materials.get(material_id)
        return Material.from_dict(material_data) if material_data else None
    
    def get_materials_by_subject(self, subject: str) -> List[Material]:
        materials = self.get_all_materials()
        return [Material.from_dict(mat) for mat in materials.values() 
                if mat.get("subject") == subject]
    
    def get_materials_by_subject_and_group(self, subject: str, group: str) -> List[Material]:
        materials = self.get_all_materials()
        if group == "all":
            return [Material.from_dict(mat) for mat in materials.values() 
                    if mat.get("subject") == subject]
        return [Material.from_dict(mat) for mat in materials.values() 
                if mat.get("subject") == subject and mat.get("group") == group]
    
    def get_materials_by_subject_and_type(self, subject: str, material_type: str) -> List[Material]:
        """Получить материалы по предмету и типу материала"""
        materials = self.get_all_materials()
        return [Material.from_dict(mat) for mat in materials.values() 
                if mat.get("subject") == subject and mat.get("material_type") == material_type]
    
    def get_recent_materials(self, limit: int = 10) -> List[Material]:
        materials = self.get_all_materials()
        sorted_materials = sorted(materials.values(), 
                               key=lambda x: x.get("date_added", ""), 
                               reverse=True)
        return [Material.from_dict(mat) for mat in sorted_materials[:limit]]

# Инициализация менеджеров
material_manager = MaterialManager()
statistics = Statistics()

# Клавиатуры
class KeyboardManager:
    @staticmethod
    def main_menu(user_id: int) -> InlineKeyboardBuilder:
        builder = InlineKeyboardBuilder()
        builder.button(text="📚 Все предметы", callback_data="all_materials")
        builder.button(text="🆕 Последние", callback_data="recent_materials")
        
        if user_id in ADMIN_IDS:
            builder.button(text="👑 Админ-панель", callback_data="admin_panel")
        
        builder.button(text="ℹ️ Помощь", callback_data="help")
        builder.adjust(2, 1, 1)
        return builder
    
    @staticmethod
    def admin_panel_keyboard() -> InlineKeyboardBuilder:
        """Главное меню админ-панели"""
        builder = InlineKeyboardBuilder()
        builder.button(text="➕ Добавить материал", callback_data="add_material")
        builder.button(text="🗑 Управление материалами", callback_data="manage_materials")
        builder.button(text="📊 Статистика", callback_data="admin_stats")
        builder.button(text="⬅️ В главное меню", callback_data="main_menu")
        builder.adjust(1)
        return builder
    
    @staticmethod
    def stats_keyboard() -> InlineKeyboardBuilder:
        """Клавиатура для статистики"""
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Общая статистика", callback_data="admin_stats")
        builder.button(text="📈 Детальная статистика", callback_data="detailed_stats")
        builder.button(text="👥 Активность пользователей", callback_data="users_stats")
        builder.button(text="📚 Популярные материалы", callback_data="popular_materials")
        builder.button(text="⬅️ В админ-панель", callback_data="admin_panel")
        builder.adjust(1)
        return builder
    
    @staticmethod
    def admin_subjects_keyboard() -> InlineKeyboardBuilder:
        """Клавиатура выбора предмета для админа"""
        builder = InlineKeyboardBuilder()
        for key, subject in SUBJECTS.items():
            builder.button(text=f"📖 {subject}", callback_data=f"admin_subject:{key}")
        builder.button(text="❌ Отмена", callback_data="admin_panel")
        builder.adjust(2)
        return builder
    
    @staticmethod
    def admin_groups_keyboard(subject: str) -> InlineKeyboardBuilder:
        builder = InlineKeyboardBuilder()
        
        if subject == "информатика":
            for group in INFORMATICS_GROUPS:
                builder.button(text=f"👥 {group}", callback_data=f"admin_group:{group}")
        else:
            builder.button(text="📚 Лекции", callback_data="admin_group:all")
        
        builder.button(text="⬅️ Назад", callback_data="admin_add_back")
        builder.button(text="❌ Отмена", callback_data="admin_panel")
        builder.adjust(2)
        return builder
    
    @staticmethod
    def admin_material_types_keyboard(subject: str) -> InlineKeyboardBuilder:
        """Клавиатура типов материалов для админа"""
        builder = InlineKeyboardBuilder()
        
        if subject in SUBJECT_TYPES:
            for material_type in SUBJECT_TYPES[subject]:
                builder.button(text=material_type, callback_data=f"admin_material_type:{material_type}")
        else:
            builder.button(text="📚 Лекции", callback_data="admin_material_type:📚 Лекции")
        
        builder.button(text="⬅️ Назад", callback_data="admin_add_back")
        builder.button(text="❌ Отмена", callback_data="admin_panel")
        builder.adjust(1)
        return builder
    
    @staticmethod
    def admin_cancel_keyboard() -> InlineKeyboardBuilder:
        builder = InlineKeyboardBuilder()
        builder.button(text="⬅️ Назад", callback_data="admin_add_back")
        builder.button(text="❌ Отмена", callback_data="admin_panel")
        builder.adjust(2)
        return builder
    
    @staticmethod
    def subjects_keyboard() -> InlineKeyboardBuilder:
        builder = InlineKeyboardBuilder()
        for key, subject in SUBJECTS.items():
            builder.button(text=f"📖 {subject}", callback_data=f"subject:{key}")
        builder.button(text="⬅️ Назад", callback_data="main_menu")
        builder.adjust(2)
        return builder
    
    @staticmethod
    def groups_keyboard(subject: str) -> InlineKeyboardBuilder:
        builder = InlineKeyboardBuilder()
        
        if subject == "информатика":
            for group in INFORMATICS_GROUPS:
                builder.button(text=f"👥 {group}", callback_data=f"group:{group}")
        else:
            builder.button(text="📚 Лекции", callback_data="group:all")
        
        builder.button(text="⬅️ Назад", callback_data="back_to_subjects")
        builder.adjust(2)
        return builder
    
    @staticmethod
    def material_types_keyboard(subject: str) -> InlineKeyboardBuilder:
        """Клавиатура с типами материалов для МДК и Архитектуры"""
        builder = InlineKeyboardBuilder()
        
        if subject in SUBJECT_TYPES:
            for material_type in SUBJECT_TYPES[subject]:
                builder.button(text=material_type, callback_data=f"material_type:{material_type}")
        else:
            builder.button(text="📚 Лекции", callback_data="material_type:📚 Лекции")
        
        builder.button(text="⬅️ Назад", callback_data="back_to_subjects")
        builder.adjust(1)
        return builder
    
    @staticmethod
    def materials_list_keyboard(materials: List[Material]) -> InlineKeyboardBuilder:
        builder = InlineKeyboardBuilder()
        
        for material in materials:
            builder.button(text=material.title, callback_data=f"material:{material.id}")
        
        builder.button(text="⬅️ Назад", callback_data="back_to_materials_list")
        builder.adjust(1)
        return builder
    
    @staticmethod
    def material_detail_keyboard(material_id: str, user_id: int) -> InlineKeyboardBuilder:
        builder = InlineKeyboardBuilder()
        builder.button(text="⬅️ Назад к материалам", callback_data="back_to_materials")
        
        if user_id in ADMIN_IDS:
            builder.button(text="🗑 Удалить", callback_data=f"delete_confirm:{material_id}")
        
        builder.adjust(1)
        return builder
    
    @staticmethod
    def manage_materials_keyboard(materials: List[Material]) -> InlineKeyboardBuilder:
        builder = InlineKeyboardBuilder()
        
        for material in materials:
            builder.button(text=f"🗑 {material.title}", callback_data=f"delete_material:{material.id}")
        
        builder.button(text="⬅️ Назад", callback_data="admin_panel")
        builder.adjust(1)
        return builder

# Исправленная система работы с файлами
class FileManager:
    @staticmethod
    async def save_media_file(message: Message, file_prefix: str) -> Optional[str]:
        """Сохранение файлов"""
        try:
            if message.document:
                file_ext = os.path.splitext(message.document.file_name)[1]
                file_name = f"{file_prefix}{file_ext}"
                file_path = os.path.join(MEDIA_DIR, file_name)
                await bot.download(message.document, destination=file_path)
                print(f"✅ Документ сохранен: {file_path}")
                return file_name
            
            elif message.photo:
                file_name = f"{file_prefix}_photo.jpg"
                file_path = os.path.join(MEDIA_DIR, file_name)
                await bot.download(message.photo[-1], destination=file_path)
                print(f"✅ Фото сохранено: {file_path}")
                return file_name
            
            elif message.video:
                file_name = f"{file_prefix}_video.mp4"
                file_path = os.path.join(MEDIA_DIR, file_name)
                await bot.download(message.video, destination=file_path)
                print(f"✅ Видео сохранено: {file_path}")
                return file_name
                
        except Exception as e:
            print(f"❌ Ошибка сохранения файла: {e}")
        return None
    
    @staticmethod
    async def send_media_file(chat_id: int, file_path: str, caption: str = ""):
        """Отправка файлов с использованием FSInputFile"""
        try:
            full_path = os.path.join(MEDIA_DIR, file_path)
            
            if not os.path.exists(full_path):
                print(f"❌ Файл не найден: {full_path}")
                return False
            
            print(f"📤 Отправка файла: {full_path}")
            
            # Используем FSInputFile вместо InputFile
            if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                await bot.send_photo(chat_id, FSInputFile(full_path), caption=caption)
            elif file_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                await bot.send_video(chat_id, FSInputFile(full_path), caption=caption)
            else:
                await bot.send_document(chat_id, FSInputFile(full_path), caption=caption)
            
            print("✅ Файл успешно отправлен!")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка отправки файла: {e}")
            return False

# Утилиты для работы с сообщениями
class MessageUtils:
    @staticmethod
    async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None):
        """Безопасное редактирование сообщения"""
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
            await callback.answer()
        except Exception as e:
            print(f"❌ Ошибка редактирования сообщения: {e}")
            await callback.answer("⚠️ Произошла ошибка", show_alert=False)
    
    @staticmethod
    async def safe_send_message(chat_id: int, text: str, reply_markup=None):
        """Безопасная отправка сообщения"""
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
            return True
        except Exception as e:
            print(f"❌ Ошибка отправки сообщения: {e}")
            return False

# Основные команды с отслеживанием статистики
@router.message(Command("start"))
async def start(message: Message):
    # Отправляем стикер
    await message.answer_sticker("CAACAgIAAxkBAAEPpXNo_iF5zvoSR-sX4u0G-TxWjbGrlQACzTIAAtyEWEgs4kVS4Lfk0DYE")
    
    # Регистрируем пользователя
    statistics.register_user(message.from_user.id)
    statistics.register_action(message.from_user.id, "start_command")
    
    welcome_text = """
👋 Добро пожаловать в бот учебных материалов!

📚 Доступные предметы:
• Информатика (группы 11-17)
• Архитектура
• ИТ (Информационные технологии)
• МДК 05.01 

Выберите действие в меню ниже:
    """
    await message.answer(
        welcome_text,
        reply_markup=KeyboardManager.main_menu(message.from_user.id).as_markup()
    )

# Обработка текстовых команд "меню", "помощь" и других
@router.message(F.text.lower().in_(["меню", "начать", "start", "главное меню"]))
async def text_menu(message: Message):
    statistics.register_action(message.from_user.id, "text_menu")
    
    await message.answer(
        "🎯 Главное меню",
        reply_markup=KeyboardManager.main_menu(message.from_user.id).as_markup()
    )

@router.message(F.text.lower().in_(["помощь", "help", "справка"]))
async def text_help(message: Message):
    statistics.register_action(message.from_user.id, "text_help")
    
    help_text = """
📚 Доступные команды:

/start - Главное меню
/help - Справка  
/recent - Последние материалы
/admin - Панель администратора

Используйте кнопки меню для удобства! 🎯
    """
    await message.answer(help_text)

@router.message(F.text.lower().in_(["админ", "admin", "админка"]))
async def text_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 Доступ запрещен")
        return
    
    await message.answer_sticker("CAACAgIAAxkBAAEPpYlo_i6hB3X4xhLe2lulwpAta0LBngACMDcAApVPWEiv_tHLqqsS0zYE")
    
    statistics.register_action(message.from_user.id, "text_admin")
    
    await message.answer(
        "👨‍💻 Панель администратора",
        reply_markup=KeyboardManager.admin_panel_keyboard().as_markup()
    )

@router.message(F.text.lower().in_(["последние", "новые", "recent"]))
async def text_recent(message: Message):
    statistics.register_action(message.from_user.id, "text_recent")
    
    recent_materials = material_manager.get_recent_materials(5)
    
    if not recent_materials:
        await message.answer("📭 Пока нет материалов.")
        return
    
    text = "🆕 Последние материалы:\n\n"
    for i, material in enumerate(recent_materials, 1):
        group_info = f" ({material.group})" if material.group and material.group != "all" else ""
        type_info = f" [{material.material_type}]" if material.material_type else ""
        text += f"{i}. {material.title} - {material.subject}{group_info}{type_info}\n"
    
    await message.answer(text)

@router.message(F.text.lower().in_(["материалы", "предметы", "все предметы"]))
async def text_materials(message: Message):
    statistics.register_action(message.from_user.id, "text_materials")
    
    await message.answer(
        "📚 Выберите предмет:",
        reply_markup=KeyboardManager.subjects_keyboard().as_markup()
    )

@router.message(F.text.lower().in_(["id", "айди", "мой id"]))
async def text_id(message: Message):
    user_id = message.from_user.id
    text = f"""
🆔 Ваши идентификаторы:

👤 User ID: {user_id}
Имя: {message.from_user.first_name}
Username: @{message.from_user.username or 'Не указан'}
    """
    await message.answer(text)

@router.message(Command("menu"))
async def menu_command(message: Message):
    statistics.register_action(message.from_user.id, "menu_command")
    
    await message.answer(
        "🎯 Главное меню",
        reply_markup=KeyboardManager.main_menu(message.from_user.id).as_markup()
    )

@router.message(Command("help"))
async def help_cmd(message: Message):
    statistics.register_action(message.from_user.id, "help_command")
    
    help_text = """
📚 Доступные команды:

/start - Главное меню
/menu - Главное меню
/help - Справка  
/id - Показать ID
/recent - Последние материалы
/admin - Панель администратора

Используйте кнопки меню для удобства! 🎯
    """
    await message.answer(help_text)

@router.message(Command("id"))
async def get_id(message: Message):
    user_id = message.from_user.id
    text = f"""
🆔 Ваши идентификаторы:

👤 User ID: {user_id}
Имя: {message.from_user.first_name}
Username: @{message.from_user.username or 'Не указан'}
    """
    await message.answer(text)

@router.message(Command("admin"))
async def admin_command(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 Доступ запрещен")
        return
    
    # Отправляем стикер для админа
    await message.answer_sticker("CAACAgIAAxkBAAEPpYlo_i6hB3X4xhLe2lulwpAta0LBngACMDcAApVPWEiv_tHLqqsS0zYE")
    
    statistics.register_action(message.from_user.id, "admin_access")
    
    await message.answer(
        "👨‍💻 Панель администратора",
        reply_markup=KeyboardManager.admin_panel_keyboard().as_markup()
    )

# АДМИН-ПАНЕЛЬ
@router.callback_query(F.data == "admin_panel")
async def admin_panel_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🚫 Доступ запрещен")
        return
    
    # Отправляем стикер для админа в колбэке
    await callback.message.answer_sticker("CAACAgIAAxkBAAEPpYlo_i6hB3X4xhLe2lulwpAta0LBngACMDcAApVPWEiv_tHLqqsS0zYE")
    
    statistics.register_action(callback.from_user.id, "admin_panel_access")
    
    await MessageUtils.safe_edit_message(
        callback,
        "👨‍💻 Панель администратора",
        KeyboardManager.admin_panel_keyboard().as_markup()
    )

# СТАТИСТИКА для админа
@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🚫 Доступ запрещен")
        return
    
    statistics.register_action(callback.from_user.id, "stats_view")
    
    materials = material_manager.get_all_materials()
    total_materials = len(materials)
    
    # Основная статистика
    total_users = statistics.data["total_users"]
    active_today = statistics.get_active_users_count_today()
    
    # Статистика по предметам
    subjects_stats = {}
    for material_data in materials.values():
        subject = material_data.get('subject', 'Неизвестно')
        if subject not in subjects_stats:
            subjects_stats[subject] = 0
        subjects_stats[subject] += 1
    
    # Статистика за последние 7 дней
    weekly_stats = statistics.get_daily_stats(7)
    total_weekly_actions = sum(day["actions"] for day in weekly_stats)
    total_weekly_users = sum(day["active_users"] for day in weekly_stats)
    
    stats_text = "📊 ОБЩАЯ СТАТИСТИКА\n\n"
    stats_text += f"👥 Всего пользователей: {total_users}\n"
    stats_text += f"🟢 Активных сегодня: {active_today}\n"
    stats_text += f"📚 Всего материалов: {total_materials}\n"
    stats_text += f"📈 Активность за неделю: {total_weekly_actions} действий\n"
    stats_text += f"👤 Уникальных за неделю: {total_weekly_users} пользователей\n\n"
    
    stats_text += "📖 Материалы по предметам:\n"
    for subject, count in subjects_stats.items():
        stats_text += f"• {subject}: {count} материалов\n"
    
    await MessageUtils.safe_edit_message(
        callback,
        stats_text,
        KeyboardManager.stats_keyboard().as_markup()
    )

@router.callback_query(F.data == "detailed_stats")
async def detailed_stats(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🚫 Доступ запрещен")
        return
    
    statistics.register_action(callback.from_user.id, "detailed_stats_view")
    
    # Статистика за последние 7 дней
    weekly_stats = statistics.get_daily_stats(7)
    
    stats_text = "📈 ДЕТАЛЬНАЯ СТАТИСТИКА ЗА 7 ДНЕЙ\n\n"
    
    for day in weekly_stats:
        date_obj = datetime.datetime.strptime(day["date"], "%Y-%m-%d").date()
        if date_obj == datetime.date.today():
            date_str = "Сегодня"
        elif date_obj == datetime.date.today() - datetime.timedelta(days=1):
            date_str = "Вчера"
        else:
            date_str = date_obj.strftime("%d.%m")
        
        stats_text += f"📅 {date_str}:\n"
        stats_text += f"   👤 Новые: {day['new_users']}\n"
        stats_text += f"   🟢 Активные: {day['active_users']}\n"
        stats_text += f"   📝 Действия: {day['actions']}\n\n"
    
    await MessageUtils.safe_edit_message(
        callback,
        stats_text,
        KeyboardManager.stats_keyboard().as_markup()
    )

@router.callback_query(F.data == "popular_materials")
async def popular_materials_stats(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🚫 Доступ запрещен")
        return
    
    statistics.register_action(callback.from_user.id, "popular_materials_view")
    
    popular_materials = statistics.get_popular_materials(10)
    
    if not popular_materials:
        stats_text = "📊 ПОПУЛЯРНЫЕ МАТЕРИАЛЫ\n\nПока нет статистики просмотров."
    else:
        stats_text = "📊 САМЫЕ ПОПУЛЯРНЫЕ МАТЕРИАЛЫ\n\n"
        
        for i, mat in enumerate(popular_materials, 1):
            material = material_manager.get_material(mat["material_id"])
            if material:
                stats_text += f"{i}. {material.title}\n"
                stats_text += f"   👀 Просмотров: {mat['views']}\n"
                stats_text += f"   📚 Предмет: {material.subject}\n\n"
    
    await MessageUtils.safe_edit_message(
        callback,
        stats_text,
        KeyboardManager.stats_keyboard().as_markup()
    )

@router.callback_query(F.data == "users_stats")
async def users_stats(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🚫 Доступ запрещен")
        return
    
    statistics.register_action(callback.from_user.id, "users_stats_view")
    
    user_actions = statistics.data["user_actions"]
    top_users = sorted(
        user_actions.items(),
        key=lambda x: x[1]["total_actions"],
        reverse=True
    )[:10]
    
    stats_text = "👥 ТОП-10 АКТИВНЫХ ПОЛЬЗОВАТЕЛЕЙ\n\n"
    
    if not top_users:
        stats_text += "Пока нет данных об активности пользователей."
    else:
        for i, (user_id, data) in enumerate(top_users, 1):
            stats_text += f"{i}. ID: {user_id}\n"
            stats_text += f"   📝 Всего действий: {data['total_actions']}\n"
            stats_text += f"   📅 Первый визит: {data['first_seen']}\n"
            stats_text += f"   🔄 Последний визит: {data['last_seen']}\n\n"
    
    await MessageUtils.safe_edit_message(
        callback,
        stats_text,
        KeyboardManager.stats_keyboard().as_markup()
    )

# АДМИН-ПАНЕЛЬ: Добавление материалов через кнопки
@router.callback_query(F.data == "add_material")
async def admin_add_material_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🚫 Доступ запрещен")
        return
    
    statistics.register_action(callback.from_user.id, "add_material_start")
    
    await state.set_state(AddMaterialStates.waiting_subject)
    await MessageUtils.safe_edit_message(
        callback,
        "📝 ДОБАВЛЕНИЕ МАТЕРИАЛА\n\nВыберите предмет:",
        KeyboardManager.admin_subjects_keyboard().as_markup()
    )

@router.callback_query(AddMaterialStates.waiting_subject, F.data.startswith("admin_subject:"))
async def admin_process_subject(callback: CallbackQuery, state: FSMContext):
    subject_key = callback.data.split(":")[1]
    subject_name = SUBJECTS[subject_key]
    
    statistics.register_action(callback.from_user.id, "subject_selected", subject_name)
    
    await state.update_data(subject_key=subject_key, subject_name=subject_name)
    
    if subject_key == "информатика":
        await state.set_state(AddMaterialStates.waiting_group)
        await MessageUtils.safe_edit_message(
            callback,
            f"📝 {subject_name}\n\nВыберите группу:",
            KeyboardManager.admin_groups_keyboard(subject_key).as_markup()
        )
    else:
        await state.set_state(AddMaterialStates.waiting_type)
        await MessageUtils.safe_edit_message(
            callback,
            f"📝 {subject_name}\n\nВыберите тип материала:",
            KeyboardManager.admin_material_types_keyboard(subject_key).as_markup()
        )

@router.callback_query(AddMaterialStates.waiting_group, F.data.startswith("admin_group:"))
async def admin_process_group_callback(callback: CallbackQuery, state: FSMContext):
    group = callback.data.split(":")[1]
    await state.update_data(group=group)
    await state.set_state(AddMaterialStates.waiting_title)
    
    data = await state.get_data()
    subject_name = data['subject_name']
    
    await MessageUtils.safe_edit_message(
        callback,
        f"📝 {subject_name}\nГруппа: {group if group != 'all' else 'Все'}\n\nВведите название материала:",
        KeyboardManager.admin_cancel_keyboard().as_markup()
    )

@router.callback_query(AddMaterialStates.waiting_type, F.data.startswith("admin_material_type:"))
async def admin_process_material_type_callback(callback: CallbackQuery, state: FSMContext):
    material_type = callback.data.split(":")[1]
    await state.update_data(material_type=material_type, group="all")
    await state.set_state(AddMaterialStates.waiting_title)
    
    data = await state.get_data()
    subject_name = data['subject_name']
    
    material_text = "лекции" if material_type == "📚 Лекции" else "практической работы"
    
    await MessageUtils.safe_edit_message(
        callback,
        f"📝 {subject_name}\nТип: {material_type}\n\nВведите название {material_text}:",
        KeyboardManager.admin_cancel_keyboard().as_markup()
    )

@router.message(AddMaterialStates.waiting_title)
async def admin_process_title(message: Message, state: FSMContext):
    if not message.text or len(message.text.strip()) == 0:
        await message.answer("❌ Название не может быть пустым. Введите название:")
        return
    
    await state.update_data(title=message.text.strip())
    await state.set_state(AddMaterialStates.waiting_description)
    
    data = await state.get_data()
    subject_name = data['subject_name']
    group_info = f"Группа: {data.get('group')}" if data.get('group') and data.get('group') != 'all' else ""
    type_info = f"Тип: {data.get('material_type')}" if data.get('material_type') else ""
    
    info_text = f"📝 {subject_name}\n{group_info}\n{type_info}\nНазвание: {message.text.strip()}\n\n"
    
    await message.answer(
        f"{info_text}Введите описание материала (или '-' чтобы пропустить):",
        reply_markup=KeyboardManager.admin_cancel_keyboard().as_markup()
    )

@router.message(AddMaterialStates.waiting_description)
async def admin_process_description(message: Message, state: FSMContext):
    description = message.text if message.text and message.text != "-" else ""
    await state.update_data(description=description)
    await state.set_state(AddMaterialStates.waiting_file)
    
    data = await state.get_data()
    subject_name = data['subject_name']
    group_info = f"Группа: {data.get('group')}" if data.get('group') and data.get('group') != 'all' else ""
    type_info = f"Тип: {data.get('material_type')}" if data.get('material_type') else ""
    
    info_text = f"📝 {subject_name}\n{group_info}\n{type_info}\nНазвание: {data['title']}\nОписание: {description or 'нет'}\n\n"
    
    await message.answer(
        f"{info_text}📎 Отправьте файл материала (документ, фото или видео):",
        reply_markup=KeyboardManager.admin_cancel_keyboard().as_markup()
    )

@router.message(AddMaterialStates.waiting_file)
async def admin_process_file(message: Message, state: FSMContext):
    data = await state.get_data()
    material_id = str(uuid.uuid4())[:8]
    
    print(f"🔍 Начало обработки файла для материала {material_id}")
    
    # Сохраняем файл
    file_name = await FileManager.save_media_file(message, material_id)
    
    if not file_name:
        await message.answer("❌ Не удалось сохранить файл. Пожалуйста, попробуйте отправить файл еще раз:")
        return
    
    # Создаем материал
    material = Material(
        material_id=material_id,
        title=data['title'],
        subject=data['subject_name'],
        group=data.get('group', ''),
        material_type=data.get('material_type', ''),
        description=data['description'],
        file_path=file_name
    )
    
    if material_manager.add_material(material):
        group_info = ""
        if material.group and material.group != "all":
            group_info = f" для группы {material.group}"
        
        type_info = ""
        if material.material_type:
            type_info = f" ({material.material_type})"
            
        success_text = (
            f"✅ Материал успешно добавлен!\n\n"
            f"📚 Название: {material.title}\n"
            f"🎯 Предмет: {material.subject}{group_info}{type_info}\n"
            f"📄 Файл: {file_name}\n"
            f"📅 Дата: {material.date_added}"
        )
        
        await message.answer(
            success_text,
            reply_markup=KeyboardManager.admin_panel_keyboard().as_markup()
        )
    else:
        await message.answer(
            "❌ Ошибка при сохранении материала.",
            reply_markup=KeyboardManager.admin_panel_keyboard().as_markup()
        )
    
    await state.clear()

# Навигация в админ-панели
@router.callback_query(F.data == "admin_add_back")
async def admin_add_back(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    
    if current_state == AddMaterialStates.waiting_group:
        await state.set_state(AddMaterialStates.waiting_subject)
        await MessageUtils.safe_edit_message(
            callback,
            "📝 ДОБАВЛЕНИЕ МАТЕРИАЛА\n\nВыберите предмет:",
            KeyboardManager.admin_subjects_keyboard().as_markup()
        )
    elif current_state == AddMaterialStates.waiting_type:
        await state.set_state(AddMaterialStates.waiting_subject)
        await MessageUtils.safe_edit_message(
            callback,
            "📝 ДОБАВЛЕНИЕ МАТЕРИАЛА\n\nВыберите предмет:",
            KeyboardManager.admin_subjects_keyboard().as_markup()
        )
    elif current_state == AddMaterialStates.waiting_title:
        data = await state.get_data()
        subject_key = data.get('subject_key')
        
        if subject_key == "информатика":
            await state.set_state(AddMaterialStates.waiting_group)
            await MessageUtils.safe_edit_message(
                callback,
                f"📝 {data['subject_name']}\n\nВыберите группа:",
                KeyboardManager.admin_groups_keyboard(subject_key).as_markup()
            )
        else:
            await state.set_state(AddMaterialStates.waiting_type)
            await MessageUtils.safe_edit_message(
                callback,
                f"📝 {data['subject_name']}\n\nВыберите тип материала:",
                KeyboardManager.admin_material_types_keyboard(subject_key).as_markup()
            )
    else:
        await state.clear()
        await admin_panel_callback(callback)

# Управление материалами (админ)
@router.callback_query(F.data == "manage_materials")
async def manage_materials_handler(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🚫 Доступ запрещен")
        return
    
    materials = material_manager.get_recent_materials(20)
    
    if not materials:
        await MessageUtils.safe_edit_message(
            callback,
            "📭 Нет материалов для управления.",
            KeyboardManager.admin_panel_keyboard().as_markup()
        )
        return
    
    text = "🗑 Управление материалами:\n\nВыберите материал для удаления:"
    
    await MessageUtils.safe_edit_message(
        callback,
        text,
        KeyboardManager.manage_materials_keyboard(materials).as_markup()
    )

@router.callback_query(F.data.startswith("delete_material:"))
async def delete_material_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🚫 Доступ запрещен")
        return
    
    material_id = callback.data.split(":")[1]
    material = material_manager.get_material(material_id)
    
    if not material:
        await callback.answer("⚠️ Материал не найден")
        return
    
    if material_manager.delete_material(material_id):
        await MessageUtils.safe_edit_message(
            callback,
            f"✅ Материал '{material.title}' удален!",
            KeyboardManager.admin_panel_keyboard().as_markup()
        )
    else:
        await callback.answer("❌ Ошибка при удалении")

@router.callback_query(F.data.startswith("delete_confirm:"))
async def delete_confirm_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("🚫 Доступ запрещен")
        return
    
    material_id = callback.data.split(":")[1]
    material = material_manager.get_material(material_id)
    
    if not material:
        await callback.answer("⚠️ Материал не найден")
        return
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"delete_material:{material_id}")
    builder.button(text="❌ Отмена", callback_data=f"material:{material_id}")
    builder.adjust(2)
    
    await MessageUtils.safe_edit_message(
        callback,
        f"⚠️ Подтверждение удаления\n\nВы уверены, что хотите удалить материал:\n{material.title}?",
        builder.as_markup()
    )

# НАВИГАЦИЯ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ
@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    statistics.register_action(callback.from_user.id, "main_menu")
    
    await MessageUtils.safe_edit_message(
        callback,
        "🎯 Главное меню",
        KeyboardManager.main_menu(callback.from_user.id).as_markup()
    )

@router.callback_query(F.data == "all_materials")
async def all_materials_callback(callback: CallbackQuery):
    statistics.register_action(callback.from_user.id, "all_materials_view")
    
    await MessageUtils.safe_edit_message(
        callback,
        "📚 Выберите предмет:",
        KeyboardManager.subjects_keyboard().as_markup()
    )

@router.callback_query(F.data == "back_to_subjects")
async def back_to_subjects(callback: CallbackQuery):
    await all_materials_callback(callback)

@router.callback_query(F.data.startswith("subject:"))
async def subject_materials_callback(callback: CallbackQuery):
    subject_key = callback.data.split(":")[1]
    subject_name = SUBJECTS.get(subject_key, subject_key)
    
    statistics.register_action(callback.from_user.id, "subject_view", subject_name)
    
    if subject_key == "информатика":
        text = f"📖 {subject_name}\n\nВыберите группу:"
        await MessageUtils.safe_edit_message(
            callback,
            text,
            KeyboardManager.groups_keyboard(subject_key).as_markup()
        )
    else:
        text = f"📖 {subject_name}\n\nВыберите тип материалов:"
        await MessageUtils.safe_edit_message(
            callback,
            text,
            KeyboardManager.material_types_keyboard(subject_key).as_markup()
        )

@router.callback_query(F.data.startswith("group:"))
async def group_materials_callback(callback: CallbackQuery):
    group = callback.data.split(":")[1]
    
    # Получаем предмет из текста сообщения
    subject_line = callback.message.text.split('\n')[0]
    subject_key = next((key for key, name in SUBJECTS.items() if name in subject_line), None)
    
    if not subject_key:
        await callback.answer("❌ Ошибка: предмет не найден")
        return
    
    subject_name = SUBJECTS[subject_key]
    materials = material_manager.get_materials_by_subject_and_group(subject_name, group)
    
    if not materials:
        group_text = f"группы {group}" if group != "all" else "лекций"
        await MessageUtils.safe_edit_message(
            callback,
            f"📭 Нет материалов по предмету {subject_name} для {group_text}.",
            KeyboardManager.groups_keyboard(subject_key).as_markup()
        )
        return
    
    group_text = f"для группы {group}" if group != "all" else "лекции"
    
    await MessageUtils.safe_edit_message(
        callback,
        f"📖 Материалы по {subject_name} {group_text}:",
        KeyboardManager.materials_list_keyboard(materials).as_markup()
    )

@router.callback_query(F.data.startswith("material_type:"))
async def material_type_callback(callback: CallbackQuery):
    material_type = callback.data.split(":")[1]
    
    # Получаем предмет из текста сообщения
    subject_line = callback.message.text.split('\n')[0]
    subject_key = next((key for key, name in SUBJECTS.items() if name in subject_line), None)
    
    if not subject_key:
        await callback.answer("❌ Ошибка: предмет не найден")
        return
    
    subject_name = SUBJECTS[subject_key]
    materials = material_manager.get_materials_by_subject_and_type(subject_name, material_type)
    
    if not materials:
        type_text = "лекций" if material_type == "📚 Лекции" else "практических работ"
        await MessageUtils.safe_edit_message(
            callback,
            f"📭 Нет {type_text} по предмету {subject_name}.",
            KeyboardManager.material_types_keyboard(subject_key).as_markup()
        )
        return
    
    await MessageUtils.safe_edit_message(
        callback,
        f"📖 {material_type} по {subject_name}:",
        KeyboardManager.materials_list_keyboard(materials).as_markup()
    )

@router.callback_query(F.data == "back_to_materials_list")
async def back_to_materials_list(callback: CallbackQuery):
    # Возвращаемся к предыдущему списку материалов
    await callback.answer("Возврат...")
    # Просто отправляем пользователя к выбору предметов
    await all_materials_callback(callback)

@router.callback_query(F.data == "back_to_materials")
async def back_to_materials(callback: CallbackQuery):
    # Возвращаемся к списку материалов текущего предмета/группы
    await callback.answer("Возврат к материалам...")
    # Пытаемся определить контекст из предыдущего сообщения
    text = callback.message.text
    if "группы" in text:
        # Если были в просмотре группы, возвращаемся к группам
        subject_line = text.split('\n')[0]
        subject_key = next((key for key, name in SUBJECTS.items() if name in subject_line), None)
        if subject_key:
            await subject_materials_callback(callback)
    else:
        # Иначе возвращаемся к предметам
        await all_materials_callback(callback)

@router.callback_query(F.data.startswith("material:"))
async def material_detail_callback(callback: CallbackQuery):
    material_id = callback.data.split(":")[1]
    material = material_manager.get_material(material_id)
    
    if not material:
        await callback.answer("⚠️ Материал не найден")
        return
    
    # Регистрируем просмотр материала
    statistics.register_action(callback.from_user.id, "material_view", material_id)
    
    group_info = f"\nГруппа: {material.group}" if material.group and material.group != "all" else ""
    type_info = f"\nТип: {material.material_type}" if material.material_type else ""
    
    # Добавляем счетчик просмотров
    views = statistics.data["material_views"].get(material_id, 0)
    
    text = f"""
📚 {material.title}

Предмет: {material.subject}{group_info}{type_info}
Дата добавления: {material.date_added}
👀 Просмотров: {views}

{material.description or "Описание отсутствует"}
    """
    
    # Сначала отправляем текст с кнопками
    await MessageUtils.safe_edit_message(
        callback,
        text,
        KeyboardManager.material_detail_keyboard(
            material_id, callback.from_user.id
        ).as_markup()
    )
    
    # Затем отправляем файл отдельным сообщением
    if material.file_path:
        print(f"📤 Попытка отправить файл материала: {material.file_path}")
        success = await FileManager.send_media_file(
            callback.from_user.id, 
            material.file_path,
            f"📎 Файл к материалу: {material.title}"
        )
        if not success:
            await callback.message.answer("⚠️ Не удалось загрузить файл. Возможно, файл был удален или поврежден.")

# Команда для просмотра последних материалов
@router.message(Command("recent"))
@router.callback_query(F.data == "recent_materials")
async def recent_materials_handler(update: Message | CallbackQuery):
    if isinstance(update, CallbackQuery):
        user_id = update.from_user.id
        message = update.message
        statistics.register_action(user_id, "recent_materials_view")
    else:
        user_id = update.from_user.id
        message = update
        statistics.register_action(user_id, "recent_command")
    
    recent_materials = material_manager.get_recent_materials(5)
    
    if not recent_materials:
        text = "📭 Пока нет материалов."
        if isinstance(update, CallbackQuery):
            await MessageUtils.safe_edit_message(update, text)
        else:
            await update.answer(text)
        return
    
    text = "🆕 Последние материалы:\n\n"
    for i, material in enumerate(recent_materials, 1):
        group_info = f" ({material.group})" if material.group and material.group != "all" else ""
        type_info = f" [{material.material_type}]" if material.material_type else ""
        text += f"{i}. {material.title} - {material.subject}{group_info}{type_info}\n"
    
    if isinstance(update, CallbackQuery):
        await MessageUtils.safe_edit_message(
            update,
            text,
            KeyboardManager.main_menu(update.from_user.id).as_markup()
        )
    else:
        await update.answer(text)

# Отмена действий
@router.callback_query(F.data == "cancel")
async def cancel_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await MessageUtils.safe_edit_message(
        callback,
        "❌ Действие отменено.",
        KeyboardManager.main_menu(callback.from_user.id).as_markup()
    )

@router.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery):
    statistics.register_action(callback.from_user.id, "help_callback")
    
    help_text = """
📚 Доступные команды:

/start - Главное меню
/menu - Главное меню
/help - Справка  
/id - Показать ID
/recent - Последние материалы
/admin - Панель администратора

Используйте кнопки меню для удобства! 🎯
    """
    await MessageUtils.safe_edit_message(
        callback,
        help_text,
        KeyboardManager.main_menu(callback.from_user.id).as_markup()
    )

# Обработка неизвестных сообщений
@router.message()
async def unknown_message(message: Message):
    # Если сообщение - это просто текст (не команда), предлагаем меню
    if message.text and not message.text.startswith('/'):
        await message.answer(
            "🤔 Не понял ваше сообщение. Используйте кнопки меню или текстовые команды:\n\n"
            "• 'меню' - Главное меню\n"
            "• 'помощь' - Справка\n" 
            "• 'материалы' - Все предметы\n"
            "• 'последние' - Новые материалы\n"
            "• 'id' - Мой ID",
            reply_markup=KeyboardManager.main_menu(message.from_user.id).as_markup()
        )
    else:
        await message.answer(
            "❓ Неизвестная команда. Используйте меню или /help",
            reply_markup=KeyboardManager.main_menu(message.from_user.id).as_markup()
        )

# Запуск бота
async def main():
    print("🤖 Бот запущен! Для остановки нажмите Ctrl+C")
    print(f"📁 Медиа директория: {os.path.abspath(MEDIA_DIR)}")
    print(f"📊 Статистика: {statistics.data['total_users']} пользователей")
    print(f"👑 Администраторы: {ADMIN_IDS}")
    
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n🛑 Бот останавливается...")
        print(f"💾 Сохранение статистики...")
        statistics.save_data()

if __name__ == "__main__":
    asyncio.run(main())